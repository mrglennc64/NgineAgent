"""NgineAgent — single-node workflow runtime (the "sequencer").

This is the honest, real implementation of the sequencer / multi-track DAW model:

    Sequencer            -> RuntimeLoop          (this module)
    Track                -> WorkflowDefinition    (a named list of steps)
    Note                 -> Step                  (type, depends_on, timeout, retry)
    Playhead             -> StepPlanner           (resolves which steps are ready)
    Heartbeat / clock    -> events on a shared JSONL bus (engine.events.v1)
    Track memory         -> per-run context dict + the event log
    Transport (play/...) -> start_workflow / stop_workflow / duplicate_workflow

It runs MANY workflows concurrently (asyncio), each with its own RunId, advancing
each track's playhead independently as steps complete. Every step invokes the REAL
vendored engine (detect/apply) — no reimplementation, no mocks, real durations.

What this is NOT (and we say so honestly in the report):
    - It is single-node. The event "bus" is an append-only JSONL file, not Kafka.
      At this volume that is the correct engineering choice; Kafka partitioned by
      RunId is the documented HORIZONTAL-SCALE migration path, not a current claim.

Run it:
    python -m ngineagent.runtime_loop
-> writes runs/BUS-<ts>.jsonl (interleaved multi-track event stream)
   then:  python -m ngineagent.run_report --bus runs/BUS-<ts>.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from ngineagent.engine.detect import detect_issues
from ngineagent.engine.apply import apply_decisions
from ngineagent.engine.report import render_health_report

ENGINE_VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"

STEP_TIMEOUTS = {"parse": 2000, "detect": 2000, "score": 1000, "apply": 2500, "render": 1500}


# --------------------------------------------------------------------------- #
# Track / Note model
# --------------------------------------------------------------------------- #
@dataclass
class Step:
    """A note on a track."""
    id: str
    type: str                       # parse | detect | score | apply | render
    label: str
    fn: Callable[[dict], dict]      # (ctx) -> metrics dict ; mutates ctx for later steps
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 0
    timeout_ms: int | None = None


@dataclass
class WorkflowDefinition:
    """A track: an ordered, dependency-linked set of notes."""
    name: str
    steps: list[Step]
    input_label: str = ""


# --------------------------------------------------------------------------- #
# StepPlanner — the playhead
# --------------------------------------------------------------------------- #
class StepPlanner:
    """Decides which steps are ready, blocked, or done. Moves the playhead."""

    @staticmethod
    def ready(defn: WorkflowDefinition, done: set[str], running: set[str]) -> list[Step]:
        out = []
        for s in defn.steps:
            if s.id in done or s.id in running:
                continue
            if all(dep in done for dep in s.depends_on):
                out.append(s)
        return out

    @staticmethod
    def complete(defn: WorkflowDefinition, done: set[str]) -> bool:
        return all(s.id in done for s in defn.steps)


# --------------------------------------------------------------------------- #
# RuntimeLoop — the sequencer / transport
# --------------------------------------------------------------------------- #
class RuntimeLoop:
    def __init__(self, bus_path: Path | None = None):
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        self.bus_path = bus_path or (RUNS_DIR / f"BUS-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl")
        self._fh = self.bus_path.open("w", encoding="utf-8")
        self._lock = asyncio.Lock()
        self.t0 = time.perf_counter()
        self._cancelled: set[str] = set()
        self.runs: list[dict] = []

    def _offset_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    async def _emit(self, event: str, run_id: str, workflow: str, trace_id: str, extra: dict | None = None):
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "t_ms": self._offset_ms(),
            "event": event,
            "run_id": run_id,
            "trace_id": trace_id,
            "engine_version": ENGINE_VERSION,
            "workflow": workflow,
        }
        if extra:
            rec.update(extra)
        async with self._lock:
            self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._fh.flush()

    def stop_workflow(self, run_id: str):
        """Transport: Stop. Cooperative cancel — no further steps are scheduled."""
        self._cancelled.add(run_id)

    async def _run_step(self, step: Step, ctx: dict, run_id: str, workflow: str, trace_id: str) -> dict:
        timeout_ms = step.timeout_ms or STEP_TIMEOUTS.get(step.type, 2000)
        start_offset = self._offset_ms()
        await self._emit("engine.step.started", run_id, workflow, trace_id,
                         {"step_id": step.id, "step_type": step.type, "label": step.label,
                          "timeout_ms": timeout_ms, "depends_on": step.depends_on})
        attempt = 0
        t_start = time.perf_counter()
        loop = asyncio.get_event_loop()
        while True:
            try:
                # real engine work runs in a thread so concurrent tracks truly interleave
                metrics = await loop.run_in_executor(None, step.fn, ctx)
                duration_ms = int((time.perf_counter() - t_start) * 1000)
                rec = {"step_id": step.id, "step_type": step.type, "label": step.label,
                       "timeout_ms": timeout_ms, "duration_ms": duration_ms,
                       "start_offset_ms": start_offset, "retries": attempt, "status": "OK"}
                rec.update(metrics or {})
                await self._emit("engine.step.completed", run_id, workflow, trace_id, rec)
                return rec
            except Exception as e:  # noqa: BLE001 — honest failure path
                if attempt < step.max_retries:
                    attempt += 1
                    await self._emit("engine.step.retry", run_id, workflow, trace_id,
                                     {"step_id": step.id, "attempt": attempt, "reason": str(e)[:120]})
                    continue
                duration_ms = int((time.perf_counter() - t_start) * 1000)
                await self._emit("engine.step.failed", run_id, workflow, trace_id,
                                 {"step_id": step.id, "step_type": step.type, "label": step.label,
                                  "duration_ms": duration_ms, "start_offset_ms": start_offset,
                                  "retries": attempt, "status": "FAILED", "error": str(e)[:200]})
                raise

    async def start_workflow(self, defn: WorkflowDefinition, run_id: str | None = None) -> dict:
        """Transport: Play. Creates a RunId, advances the playhead until the track ends."""
        run_id = run_id or ("RUN-" + secrets.token_hex(3))
        trace_id = uuid.uuid4().hex
        t_run0 = time.perf_counter()
        await self._emit("engine.workflow.started", run_id, defn.name, trace_id,
                         {"def": defn.input_label, "engine_version": ENGINE_VERSION,
                          "step_count": len(defn.steps)})
        ctx: dict = {}
        done: set[str] = set()
        running: set[str] = set()
        steps_done: list[dict] = []
        planner = StepPlanner()
        failed = False
        # These engine workflows are linear chains, but the planner resolves by
        # dependency — a fan-out DAG would advance multiple notes at once here.
        while not planner.complete(defn, done):
            if run_id in self._cancelled:
                await self._emit("engine.workflow.cancelled", run_id, defn.name, trace_id,
                                 {"completed_steps": len(done)})
                break
            ready = planner.ready(defn, done, running)
            if not ready:
                break
            for step in ready:
                running.add(step.id)
            results = await asyncio.gather(
                *[self._run_step(s, ctx, run_id, defn.name, trace_id) for s in ready],
                return_exceptions=True)
            for step, res in zip(ready, results):
                running.discard(step.id)
                if isinstance(res, Exception):
                    failed = True
                else:
                    done.add(step.id)
                    steps_done.append(res)
            if failed:
                break
        total_ms = int((time.perf_counter() - t_run0) * 1000)
        status = "COMPLETED" if planner.complete(defn, done) else (
            "CANCELLED" if run_id in self._cancelled else "FAILED")
        await self._emit("engine.workflow.completed", run_id, defn.name, trace_id,
                         {"status": status, "total_ms": total_ms, "steps": len(done)})
        summary = {"run_id": run_id, "workflow": defn.name, "status": status,
                   "total_ms": total_ms, "steps": steps_done}
        self.runs.append(summary)
        return summary

    async def duplicate_workflow(self, defn: WorkflowDefinition) -> dict:
        """Transport: Duplicate. Same definition, brand-new RunId."""
        return await self.start_workflow(defn)

    async def play(self, defns: list[WorkflowDefinition]) -> list[dict]:
        """Press play on several tracks at once — true multi-track concurrency."""
        return list(await asyncio.gather(*[self.start_workflow(d) for d in defns]))

    def close(self):
        self._fh.close()


# --------------------------------------------------------------------------- #
# Step factories over the REAL vendored engine
# --------------------------------------------------------------------------- #
def _validation_track(name: str, catalog_path: Path) -> WorkflowDefinition:
    def parse(ctx):
        ctx["text"] = catalog_path.read_text(encoding="utf-8")
        rows = [ln for ln in ctx["text"].replace("\r\n", "\n").split("\n") if ln.strip()]
        return {"rows_in": max(0, len(rows) - 1)}

    def detect(ctx):
        scan = detect_issues(ctx["text"])
        ctx["scan"] = scan
        return {"works": len(scan.titles), "issues_found": len(scan.issues),
                "blocking": scan.blocking, "resolvable": scan.resolvable}

    def score(ctx):
        return {"score": ctx["scan"].score}

    def render(ctx):
        html = render_health_report(ctx["scan"], scan_id=name,
                                    scan_date=datetime.now().strftime("%Y-%m-%d"))
        return {"html_bytes": len(html.encode("utf-8"))}

    return WorkflowDefinition(name, input_label=catalog_path.name, steps=[
        Step("s1", "parse", "Parse catalog CSV", parse),
        Step("s2", "detect", "Detect metadata issues", detect, depends_on=["s1"]),
        Step("s3", "score", "Compute health score", score, depends_on=["s2"]),
        Step("s4", "render", "Render health report", render, depends_on=["s3"]),
    ])


def _correction_track(name: str, catalog_path: Path, worksheet_path: Path) -> WorkflowDefinition:
    def parse(ctx):
        ctx["text"] = catalog_path.read_text(encoding="utf-8")
        ctx["ws"] = worksheet_path.read_text(encoding="utf-8")
        rows = [ln for ln in ctx["text"].replace("\r\n", "\n").split("\n") if ln.strip()]
        return {"rows_in": max(0, len(rows) - 1)}

    def detect_before(ctx):
        b = detect_issues(ctx["text"]); ctx["before"] = b
        return {"issues_found": len(b.issues), "score_before": b.score}

    def apply(ctx):
        a = apply_decisions(ctx["text"], ctx["ws"]); ctx["applied"] = a
        return {"accept": a.accept, "reject": a.reject, "edit": a.edit, "decisions": len(a.log)}

    def detect_after(ctx):
        af = detect_issues(ctx["applied"].cleaned_csv); ctx["after"] = af
        return {"issues_after": len(af.issues), "score_after": af.score,
                "score_delta": af.score - ctx["before"].score}

    def render(ctx):
        html = render_health_report(ctx["after"], scan_id=name,
                                    scan_date=datetime.now().strftime("%Y-%m-%d"))
        return {"html_bytes": len(html.encode("utf-8"))}

    return WorkflowDefinition(name, input_label=catalog_path.name, steps=[
        Step("s1", "parse", "Parse catalog + worksheet", parse),
        Step("s2", "detect", "Detect issues (before)", detect_before, depends_on=["s1"]),
        Step("s3", "apply", "Apply publisher decisions", apply, depends_on=["s2"]),
        Step("s4", "detect", "Detect issues (after)", detect_after, depends_on=["s3"]),
        Step("s5", "render", "Render after-cleaning report", render, depends_on=["s4"]),
    ])


def default_tracks() -> list[WorkflowDefinition]:
    """The real tracks shipped for the demo run — all use real samples in this repo."""
    s = ROOT / "samples"
    tracks = []
    cat = s / "catalog-en-15.csv"
    ws = s / "corrections-en-15-filled.csv"
    bench = s / "benchmark-1500.csv"
    if cat.exists():
        tracks.append(_validation_track("metadata_validation", cat))
    if cat.exists() and ws.exists():
        tracks.append(_correction_track("catalog_correction", cat, ws))
    if bench.exists():
        tracks.append(_validation_track("benchmark_validation", bench))
    if not tracks:
        sys.exit("ERROR: no sample catalogs found under samples/ — cannot run a real multi-track session.")
    return tracks


async def _main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bus", help="Output bus JSONL path (default runs/BUS-<ts>.jsonl)")
    args = p.parse_args()

    loop = RuntimeLoop(Path(args.bus) if args.bus else None)
    tracks = default_tracks()
    print(f"RuntimeLoop: pressing play on {len(tracks)} tracks concurrently...")
    summaries = await loop.play(tracks)
    loop.close()
    print(f"\nBus event log: {loop.bus_path}")
    for sm in summaries:
        print(f"  [{sm['status']:9}] {sm['workflow']:22} {sm['run_id']}  "
              f"{len(sm['steps'])} steps  {sm['total_ms']}ms")
    print(f"\nRender:  python -m ngineagent.run_report --bus {loop.bus_path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
