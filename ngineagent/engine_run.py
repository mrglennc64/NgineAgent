"""NgineAgent — instrumented run-wrapper for the metadata validation/correction engine.

Runs the REAL engine (vendored in ngineagent/engine/) and emits structured
telemetry to an append-only JSONL event log. This is the "event stream" that
makes the engine observable — without needing Kafka. Every number in the
downstream run report comes from these real events.

Event vocabulary (engine.events.v1):
    engine.run.started
    engine.step.started
    engine.step.completed   (status=OK)
    engine.step.retry       (only emitted on a genuine retry — none expected for
                             these pure deterministic steps; 0 retries is honest)
    engine.run.completed

Usage:
    python -m ngineagent.engine_run --catalog samples/test-15-mixed.csv
    python -m ngineagent.engine_run --catalog samples/test-15-mixed.csv \
        --corrections samples/corrections-worksheet-test-15-filled.csv \
        --run-id RUN-201

The wrapper imports engine functions directly — it does NOT reimplement them.
No Celery / Postgres / Redis / S3 required: the engine core is pure Python.
"""
from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Engine version stamped onto every event — matches the deployed engine
# (Generic Validation/Correction Engine, engine.usesmpt.com).
ENGINE_VERSION = "0.1.0"

# Vendored real engine — same code that powers CIP / DIP / HeyRoya / Kataloghub
from ngineagent.engine.detect import detect_issues
from ngineagent.engine.apply import apply_decisions
from ngineagent.engine.report import render_health_report

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
REPORTS_DIR = ROOT / "reports"

# Declared per-step timeout budgets (ms). The report shows declared budget vs.
# measured duration — same pattern as the AgentOS-core step table.
STEP_TIMEOUTS = {
    "parse":    2000,
    "detect":   2000,
    "score":    1000,
    "apply":    2500,
    "render":   1500,
}


class RunLogger:
    """Times steps and appends engine.events.v1 records to a JSONL log."""

    def __init__(self, run_id: str, workflow: str, definition: str, session_id: str | None = None):
        self.run_id = run_id
        self.workflow = workflow
        self.definition = definition
        # Distributed-trace identifiers — a real run is traceable end to end.
        self.trace_id = uuid.uuid4().hex
        self.session_id = session_id or ("sess-" + secrets.token_hex(4))
        self.engine_version = ENGINE_VERSION
        self.t0 = time.perf_counter()
        self.events: list[dict] = []
        self.steps: list[dict] = []
        self._step_counter = 0
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.log_path = RUNS_DIR / f"{run_id}.jsonl"
        self._fh = self.log_path.open("w", encoding="utf-8")
        self._emit("engine.run.started", {
            "def": definition,
            "engine_version": self.engine_version,
        })

    def _now_offset_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def _emit(self, event: str, extra: dict | None = None):
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "t_ms": self._now_offset_ms(),
            "event": event,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "engine_version": self.engine_version,
            "workflow": self.workflow,
        }
        if extra:
            rec.update(extra)
        self.events.append(rec)
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fh.flush()

    def step(self, step_type: str, label: str):
        """Context manager: emits started + completed, measures real duration.

        Yields a dict the caller fills with real per-step metrics; those metrics
        are attached to the engine.step.completed event.
        """
        self._step_counter += 1
        step_id = f"step_{self._step_counter}"
        timeout_ms = STEP_TIMEOUTS.get(step_type, 2000)
        return _StepCtx(self, step_id, step_type, label, timeout_ms)

    def finish(self, status: str = "OK"):
        total_ms = self._now_offset_ms()
        self._emit("engine.run.completed", {
            "status": status,
            "total_ms": total_ms,
            "steps": len(self.steps),
        })
        self._fh.close()
        return total_ms


class _StepCtx:
    def __init__(self, logger: RunLogger, step_id, step_type, label, timeout_ms):
        self.logger = logger
        self.step_id = step_id
        self.step_type = step_type
        self.label = label
        self.timeout_ms = timeout_ms
        self.metrics: dict = {}
        self.retries = 0

    def __enter__(self):
        self.start_offset = self.logger._now_offset_ms()
        self.t_start = time.perf_counter()
        self.logger._emit("engine.step.started", {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "label": self.label,
            "timeout_ms": self.timeout_ms,
        })
        return self

    def retry(self, reason: str):
        """Record a genuine retry. (Not used by the deterministic engine steps,
        but supported so the telemetry is honest if a step ever does retry.)"""
        self.retries += 1
        self.logger._emit("engine.step.retry", {
            "step_id": self.step_id,
            "attempt": self.retries,
            "reason": reason,
        })

    def __exit__(self, exc_type, exc, tb):
        duration_ms = int((time.perf_counter() - self.t_start) * 1000)
        status = "OK" if exc_type is None else "FAILED"
        completed = {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "label": self.label,
            "timeout_ms": self.timeout_ms,
            "duration_ms": duration_ms,
            "start_offset_ms": self.start_offset,
            "retries": self.retries,
            "status": status,
        }
        completed.update(self.metrics)
        self.logger.steps.append(completed)
        self.logger._emit("engine.step.completed", completed)
        return False  # never swallow exceptions


def _gen_run_id() -> str:
    return "RUN-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def run_validation(catalog_path: Path, run_id: str, session_id: str | None = None) -> dict:
    """parse -> detect -> score -> render. Returns a summary dict."""
    text = catalog_path.read_text(encoding="utf-8")
    log = RunLogger(run_id, workflow="metadata_validation", definition=catalog_path.name, session_id=session_id)

    with log.step("parse", "Parse catalog CSV") as s:
        # parsing happens inside detect_issues; we measure a cheap line count here
        rows = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
        s.metrics["rows_in"] = max(0, len(rows) - 1)

    scan = None
    with log.step("detect", "Detect metadata issues") as s:
        scan = detect_issues(text)
        s.metrics.update({
            "works": len(scan.titles),
            "contribs": scan.total_contribs,
            "issues_found": len(scan.issues),
            "blocking": scan.blocking,
            "resolvable": scan.resolvable,
        })

    with log.step("score", "Compute CWR health score") as s:
        s.metrics["score"] = scan.score

    html = None
    with log.step("render", "Render health report") as s:
        html = render_health_report(scan, scan_id=run_id, scan_date=datetime.now().strftime("%Y-%m-%d"))
        s.metrics["html_bytes"] = len(html.encode("utf-8"))

    total_ms = log.finish("OK")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    health_path = REPORTS_DIR / f"{run_id}_HEALTH-REPORT.html"
    health_path.write_text(html, encoding="utf-8")

    return {
        "run_id": run_id, "workflow": "metadata_validation",
        "total_ms": total_ms, "score": scan.score,
        "issues": len(scan.issues), "blocking": scan.blocking,
        "resolvable": scan.resolvable, "log": str(log.log_path),
        "health_report": str(health_path),
    }


def run_correction(catalog_path: Path, worksheet_path: Path, run_id: str, session_id: str | None = None) -> dict:
    """parse -> detect(before) -> apply -> detect(after) -> render(before+after)."""
    text = catalog_path.read_text(encoding="utf-8")
    worksheet = worksheet_path.read_text(encoding="utf-8")
    log = RunLogger(run_id, workflow="catalog_correction", definition=catalog_path.name, session_id=session_id)

    with log.step("parse", "Parse catalog CSV") as s:
        rows = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
        wrows = [ln for ln in worksheet.replace("\r\n", "\n").split("\n") if ln.strip()]
        s.metrics["rows_in"] = max(0, len(rows) - 1)
        s.metrics["worksheet_rows"] = max(0, len(wrows) - 1)

    before = None
    with log.step("detect", "Detect issues (before)") as s:
        before = detect_issues(text)
        s.metrics.update({
            "works": len(before.titles), "issues_found": len(before.issues),
            "blocking": before.blocking, "resolvable": before.resolvable,
            "score_before": before.score,
        })

    applied = None
    with log.step("apply", "Apply publisher decisions") as s:
        applied = apply_decisions(text, worksheet)
        s.metrics.update({
            "accept": applied.accept, "reject": applied.reject,
            "edit": applied.edit, "decisions": len(applied.log),
        })

    after = None
    with log.step("detect", "Detect issues (after)") as s:
        after = detect_issues(applied.cleaned_csv)
        s.metrics.update({
            "issues_after": len(after.issues), "blocking_after": after.blocking,
            "resolvable_after": after.resolvable, "score_after": after.score,
            "score_delta": after.score - before.score,
        })

    html_after = None
    with log.step("render", "Render after-cleaning report") as s:
        html_after = render_health_report(after, scan_id=run_id, scan_date=datetime.now().strftime("%Y-%m-%d"))
        s.metrics["html_bytes"] = len(html_after.encode("utf-8"))

    total_ms = log.finish("OK")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    after_path = REPORTS_DIR / f"{run_id}_AFTER-REPORT.html"
    after_path.write_text(html_after, encoding="utf-8")
    cleaned_path = REPORTS_DIR / f"{run_id}_CLEANED.csv"
    cleaned_path.write_text(applied.cleaned_csv, encoding="utf-8")

    return {
        "run_id": run_id, "workflow": "catalog_correction",
        "total_ms": total_ms,
        "score_before": before.score, "score_after": after.score,
        "score_delta": after.score - before.score,
        "decisions": len(applied.log),
        "log": str(log.log_path), "after_report": str(after_path),
        "cleaned_csv": str(cleaned_path),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--catalog", required=True, help="Path to catalog CSV")
    p.add_argument("--corrections", help="Path to filled correction worksheet CSV (triggers a correction run)")
    p.add_argument("--run-id", help="Run id (default: RUN-<timestamp>)")
    args = p.parse_args()

    catalog_path = Path(args.catalog)
    if not catalog_path.exists():
        print(f"[ERR] catalog not found: {catalog_path}", file=sys.stderr)
        return 1

    run_id = args.run_id or _gen_run_id()

    if args.corrections:
        ws = Path(args.corrections)
        if not ws.exists():
            print(f"[ERR] worksheet not found: {ws}", file=sys.stderr)
            return 1
        summary = run_correction(catalog_path, ws, run_id)
    else:
        summary = run_validation(catalog_path, run_id)

    print(f"\n=== {summary['workflow']} complete: {run_id} ===")
    for k, v in summary.items():
        if k in ("run_id", "workflow"):
            continue
        print(f"  {k:18} {v}")
    print(f"\nEvent log: {summary['log']}")
    print(f"Render the run report with:  python -m ngineagent.run_report --run {run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
