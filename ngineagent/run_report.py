"""NgineAgent — Engine Run Report generator.

Reads one or more engine.events.v1 JSONL logs (produced by engine_run.py) and
renders a branded HTML + PDF report with five sections:

    §1 Executive Summary       — per-run cards + aggregate metrics
    §2 Workflow Execution Timeline — CSS Gantt bars (proportional to real durations)
    §3 Step Execution Details  — full step table
    §4 Event Stream            — the raw engine.events.v1 log
    §5 Performance Metrics     — throughput, retry rate, success rate, mean/p99

EVERY value is computed from the real event log. If a log is missing or has no
completed run, the generator EXITS WITH AN ERROR rather than emit placeholder
numbers — a hollow demo destroys credibility faster than no demo.

Usage:
    python -m ngineagent.run_report --run RUN-DEMO-VAL
    python -m ngineagent.run_report --run RUN-DEMO-VAL --run RUN-DEMO-CORR
    python -m ngineagent.run_report --all
    python -m ngineagent.run_report --run RUN-DEMO-CORR --no-pdf
"""
from __future__ import annotations

import argparse
import html as _html
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "runs"
REPORTS_DIR = ROOT / "reports"

# Brand palette — matches ngineagent/engine/report.py (HeyRoya teal)
TEAL = "#1dd4b7"
AMBER = "#f2b36a"
RED = "#f87171"
BG = "#0a0f0d"
SURFACE = "#0f1714"
INK = "#e8f5f0"
INK_MUTED = "#7c9a90"
BORDER = "rgba(29,212,183,0.18)"


def load_run(run_id: str) -> dict:
    """Load + validate one run's events. Raises if missing/empty/incomplete."""
    path = RUNS_DIR / f"{run_id}.jsonl"
    if not path.exists():
        raise SystemExit(f"[ERR] run log not found: {path}\n"
                         f"      Generate it first: python -m ngineagent.engine_run --catalog <csv> --run-id {run_id}")
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    if not events:
        raise SystemExit(f"[ERR] run log is empty: {path} — refusing to render a report with no data.")

    started = next((e for e in events if e["event"] == "engine.run.started"), None)
    completed = next((e for e in events if e["event"] == "engine.run.completed"), None)
    if not started or not completed:
        raise SystemExit(f"[ERR] run {run_id} has no start/complete event — incomplete run, refusing to render.")

    steps = [e for e in events if e["event"] == "engine.step.completed"]
    if not steps:
        raise SystemExit(f"[ERR] run {run_id} has no completed steps — refusing to render.")

    return {
        "run_id": run_id,
        "workflow": started.get("workflow", "?"),
        "definition": started.get("def", ""),
        "started_ts": started["ts"],
        "trace_id": started.get("trace_id", ""),
        "session_id": started.get("session_id", ""),
        "engine_version": started.get("engine_version", ""),
        "total_ms": completed.get("total_ms", 0),
        "events": events,
        "steps": steps,
        "retries": sum(s.get("retries", 0) for s in steps),
        "ok": all(s.get("status") == "OK" for s in steps),
    }


def _pct(n, d):
    return (100.0 * n / d) if d else 0.0


def _p99(values):
    if not values:
        return 0
    s = sorted(values)
    idx = min(len(s) - 1, int(round(0.99 * (len(s) - 1))))
    return s[idx]


def esc(v) -> str:
    return _html.escape("" if v is None else str(v))


# ── Section renderers ──────────────────────────────────────────────────────────
def render_overview() -> str:
    """§0 — human-readable context. Buyers need to know what they're looking at
    before the telemetry. Static, accurate prose (no metrics here)."""
    return f"""
    <section>
      <div class="sec-tag">OVERVIEW</div>
      <h2>What this is</h2>
      <div class="ov-grid">
        <div class="ov">
          <div class="ov-k">Engine</div>
          <div class="ov-v">Generic Validation &amp; Correction Engine — the metadata
          compliance engine behind CIP, DIP, HeyRoya and Kataloghub.</div>
        </div>
        <div class="ov">
          <div class="ov-k">What it does</div>
          <div class="ov-v">Detects and corrects the metadata defects that block a music
          catalog from CWR submission — across 8 issue types — and scores CWR readiness
          0–100.</div>
        </div>
        <div class="ov">
          <div class="ov-k">Input</div>
          <div class="ov-v">A catalog CSV (title, name, role, share %, IPI, society, ISWC,
          ISRC) and, for correction, a publisher-decision worksheet.</div>
        </div>
        <div class="ov">
          <div class="ov-k">Output</div>
          <div class="ov-v">A health score + issue list, a corrected/cleaned catalog CSV,
          and a branded health report — plus the telemetry in this run report.</div>
        </div>
        <div class="ov ov-wide">
          <div class="ov-k">Why it matters</div>
          <div class="ov-v">Unclean metadata is the #1 cause of rejected CWR filings and
          mis-routed royalties. This report is generated from real engine runs on real
          catalogs — the numbers below are measured, not illustrative — so the engine's
          behaviour is observable, traceable, and auditable end to end.</div>
        </div>
      </div>
    </section>"""


def render_exec_summary(runs: list[dict]) -> str:
    total_steps = sum(len(r["steps"]) for r in runs)
    total_retries = sum(r["retries"] for r in runs)
    ok_steps = sum(1 for r in runs for s in r["steps"] if s.get("status") == "OK")
    max_dur = max((r["total_ms"] for r in runs), default=0)
    success = _pct(ok_steps, total_steps)

    cards = ""
    for r in runs:
        # critical path = linear chain = sum of step durations
        crit = sum(s.get("duration_ms", 0) for s in r["steps"])
        status_color = TEAL if r["ok"] else RED
        cards += f"""
        <div class="case">
          <div class="case-head">
            <span class="case-name">{esc(r['workflow'])}</span>
            <span class="badge" style="color:{status_color};border-color:{status_color}">{'COMPLETED' if r['ok'] else 'FAILED'}</span>
          </div>
          <div class="kv"><span>RunId</span><b>{esc(r['run_id'])}</b></div>
          <div class="kv"><span>TraceId</span><b class="mono">{esc((r['trace_id'] or '')[:16])}</b></div>
          <div class="kv"><span>Definition</span><b>{esc(r['definition'])}</b></div>
          <div class="kv"><span>Engine</span><b>v{esc(r['engine_version'] or '?')}</b></div>
          <div class="kv"><span>Steps</span><b>{len(r['steps'])}</b></div>
          <div class="kv"><span>Total Duration</span><b>{r['total_ms']}ms</b></div>
          <div class="kv"><span>Critical Path</span><b>{crit}ms (linear chain)</b></div>
          <div class="kv"><span>Retries</span><b>{r['retries']}</b></div>
        </div>"""

    metrics = [
        (str(len(runs)), "WORKFLOWS"),
        (str(total_steps), "TOTAL STEPS"),
        (f"{success:.0f}%", "SUCCESS RATE"),
        (str(total_retries), "RETRIES"),
        (f"{max_dur}ms", "MAX DURATION"),
    ]
    mcards = "".join(
        f'<div class="metric"><div class="metric-val">{esc(v)}</div><div class="metric-lbl">{esc(l)}</div></div>'
        for v, l in metrics
    )
    return f"""
    <section>
      <div class="sec-tag">SECTION 1</div>
      <h2>Executive Summary</h2>
      <div class="cases">{cards}</div>
      <div class="metrics">{mcards}</div>
    </section>"""


def render_timeline(runs: list[dict]) -> str:
    blocks = ""
    palette = ["#38bdf8", "#a78bfa", TEAL, AMBER, "#f472b6", "#fb923c"]
    for r in runs:
        max_end = max((s.get("start_offset_ms", 0) + s.get("duration_ms", 0) for s in r["steps"]), default=1)
        scale = max(max_end, 1)
        rows = ""
        for i, s in enumerate(r["steps"]):
            start = s.get("start_offset_ms", 0)
            dur = s.get("duration_ms", 0)
            left = _pct(start, scale)
            # proportional width, but a visible minimum so sub-ms bars still render;
            # the LABEL always shows the real measured duration (honest)
            width = max(_pct(dur, scale), 6.0)
            color = palette[i % len(palette)]
            rows += f"""
            <div class="tl-row">
              <div class="tl-label">{esc(s.get('label', s.get('step_type','')))}</div>
              <div class="tl-track">
                <div class="tl-bar" style="left:{left:.1f}%;width:{width:.1f}%;background:{color}">
                  <span>{dur}ms</span>
                </div>
              </div>
            </div>"""
        blocks += f"""
        <div class="tl-block">
          <div class="tl-title">{esc(r['workflow'])} · {esc(r['run_id'])} · {r['total_ms']}ms total</div>
          {rows}
        </div>"""
    return f"""
    <section>
      <div class="sec-tag">SECTION 2</div>
      <h2>Workflow Execution Timeline</h2>
      {blocks}
    </section>"""


def render_step_table(runs: list[dict]) -> str:
    rows = ""
    for r in runs:
        for s in r["steps"]:
            st_color = TEAL if s.get("status") == "OK" else RED
            ret = s.get("retries", 0)
            ret_disp = f'<span style="color:{AMBER}">{ret}</span>' if ret else "0"
            rows += f"""
            <tr>
              <td>{esc(r['workflow'])}</td>
              <td class="mono">{esc(s.get('step_id'))}</td>
              <td>{esc(s.get('step_type'))}</td>
              <td class="label-cell">{esc(s.get('label'))}</td>
              <td class="mono">{s.get('duration_ms',0)}ms</td>
              <td class="mono">{s.get('timeout_ms',0)}ms</td>
              <td class="mono">{ret_disp}</td>
              <td class="mono" style="color:{st_color}">{esc(s.get('status'))}</td>
              <td class="mono">T+{s.get('start_offset_ms',0):05d}ms</td>
            </tr>"""
    return f"""
    <section>
      <div class="sec-tag">SECTION 3</div>
      <h2>Step Execution Details</h2>
      <table>
        <thead><tr>
          <th>Workflow</th><th>Step ID</th><th>Type</th><th>Label</th>
          <th>Duration</th><th>Timeout</th><th>Retries</th><th>Status</th><th>Start</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>"""


def render_event_stream(runs: list[dict]) -> str:
    # merge all events, keep chronological by (run order, t_ms)
    rows = ""
    for r in runs:
        for e in r["events"]:
            ev = e["event"]
            ev_color = {
                "engine.run.started": TEAL, "engine.run.completed": TEAL,
                "engine.step.started": "#38bdf8", "engine.step.completed": INK_MUTED,
                "engine.step.retry": AMBER,
            }.get(ev, INK_MUTED)
            detail = e.get("label") or e.get("def") or ""
            extra = []
            for k in ("issues_found", "score", "score_before", "score_after", "score_delta",
                      "accept", "edit", "reject", "decisions", "status", "total_ms"):
                if k in e:
                    extra.append(f"{k}={e[k]}")
            detail2 = ("  " + " ".join(extra)) if extra else ""
            rows += (f'<div class="ev"><span class="ev-t">T+{e.get("t_ms",0):05d}ms</span>'
                     f'<span class="ev-run">[{esc(r["run_id"])}]</span>'
                     f'<span class="ev-name" style="color:{ev_color}">{esc(ev)}</span>'
                     f'<span class="ev-detail">{esc(detail)}{esc(detail2)}</span></div>')
    n_events = sum(len(r["events"]) for r in runs)
    return f"""
    <section>
      <div class="sec-tag">SECTION 4</div>
      <h2>Event Stream</h2>
      <div class="topic">Topic: engine.events.v1 · {n_events} events · partitioned by RunId</div>
      <div class="stream">{rows}</div>
    </section>"""


def render_perf_metrics(runs: list[dict]) -> str:
    all_durs = [s.get("duration_ms", 0) for r in runs for s in r["steps"]]
    total_steps = len(all_durs)
    total_retries = sum(r["retries"] for r in runs)
    total_events = sum(len(r["events"]) for r in runs)
    total_ms = sum(r["total_ms"] for r in runs)
    ok_steps = sum(1 for r in runs for s in r["steps"] if s.get("status") == "OK")
    mean_dur = (sum(all_durs) / total_steps) if total_steps else 0
    p99 = _p99(all_durs)
    eps = (total_events / (total_ms / 1000.0)) if total_ms else 0
    crit_pipeline = max((sum(s.get("duration_ms", 0) for s in r["steps"]) for r in runs), default=0)

    metrics = [
        (f"{eps:,.0f}", "EVENTS / SEC"),
        (str(total_steps), "STEPS EXECUTED"),
        (f"{_pct(total_retries, total_steps):.1f}%", "RETRY RATE"),
        (f"{_pct(ok_steps, total_steps):.0f}%", "SUCCESS RATE"),
        (f"{mean_dur:.0f}ms", "MEAN STEP DURATION"),
        (f"{p99}ms", "P99 STEP DURATION"),
        (f"{total_ms}ms", "TOTAL RUNTIME"),
        (f"{crit_pipeline}ms", "CRITICAL PATH (MAX)"),
    ]
    mcards = "".join(
        f'<div class="metric"><div class="metric-val">{esc(v)}</div><div class="metric-lbl">{esc(l)}</div></div>'
        for v, l in metrics
    )
    return f"""
    <section>
      <div class="sec-tag">SECTION 5</div>
      <h2>Performance Metrics</h2>
      <div class="metrics metrics-4">{mcards}</div>
    </section>"""


def render_report(runs: list[dict]) -> str:
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_ok = all(r["ok"] for r in runs)
    status_pill = f'<span class="pill" style="color:{TEAL}">● All Workflows Completed</span>' if all_ok \
        else f'<span class="pill" style="color:{RED}">● Attention — see step table</span>'
    body = (render_overview() + render_exec_summary(runs) + render_timeline(runs)
            + render_step_table(runs) + render_event_stream(runs) + render_perf_metrics(runs))
    # header trace chips from the first run (the "real distributed system" signal)
    sess = runs[0].get("session_id", "")
    ver = runs[0].get("engine_version", "")
    trace_chips = (f'<span class="pill" style="color:{INK_MUTED}">session: {esc(sess)}</span>'
                   f'<span class="pill" style="color:{INK_MUTED}">engine v{esc(ver)}</span>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>NgineAgent Run Report</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'JetBrains Mono','SF Mono',Menlo,monospace; background: {BG}; color: {INK}; padding: 40px; line-height: 1.5; }}
  .header {{ display:flex; align-items:center; gap:16px; border-bottom:2px solid {TEAL}; padding-bottom:18px; margin-bottom:22px; }}
  .logo {{ width:46px;height:46px;border-radius:10px;background:linear-gradient(135deg,{TEAL},#0f5d3f);flex-shrink:0; }}
  .h-title {{ font-size:22px;font-weight:800;color:{TEAL};letter-spacing:-0.5px; }}
  .h-sub {{ font-size:11px;color:{INK_MUTED};margin-top:3px; }}
  .pill {{ font-size:11px;border:1px solid currentColor;border-radius:999px;padding:3px 12px;margin-right:8px; }}
  .pills {{ margin: 14px 0 28px; }}
  section {{ background:{SURFACE};border:1px solid {BORDER};border-radius:12px;padding:24px;margin-bottom:18px; break-inside: avoid; }}
  .sec-tag {{ display:inline-block;font-size:9px;letter-spacing:2px;color:{TEAL};border:1px solid {TEAL};border-radius:999px;padding:2px 10px;margin-bottom:12px; }}
  h2 {{ font-size:18px;font-weight:700;margin-bottom:16px;color:{INK}; }}
  .cases {{ display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px; }}
  .case {{ background:{BG};border:1px solid {BORDER};border-radius:10px;padding:16px; }}
  .case-head {{ display:flex;justify-content:space-between;align-items:center;margin-bottom:12px; }}
  .case-name {{ font-weight:700;font-size:14px; }}
  .badge {{ font-size:9px;border:1px solid;border-radius:999px;padding:2px 10px;font-weight:600; }}
  .kv {{ display:flex;justify-content:space-between;font-size:11px;padding:4px 0;border-bottom:1px solid rgba(124,154,144,0.12); }}
  .kv span {{ color:{INK_MUTED}; }} .kv b {{ color:{INK};font-weight:600; }}
  .metrics {{ display:grid;grid-template-columns:repeat(5,1fr);gap:10px; }}
  .metrics-4 {{ grid-template-columns:repeat(4,1fr); }}
  .metric {{ background:{BG};border:1px solid {BORDER};border-radius:8px;padding:14px;text-align:center; }}
  .metric-val {{ font-size:22px;font-weight:800;color:{TEAL}; }}
  .metric-lbl {{ font-size:8px;letter-spacing:1.2px;color:{INK_MUTED};margin-top:5px; }}
  .tl-block {{ margin-bottom:18px; }}
  .tl-title {{ font-size:11px;color:{INK_MUTED};margin-bottom:8px; }}
  .tl-row {{ display:flex;align-items:center;gap:12px;margin-bottom:6px; }}
  .tl-label {{ width:200px;font-size:11px;color:{INK_MUTED};text-align:right;flex-shrink:0; }}
  .tl-track {{ flex:1;position:relative;height:24px;background:{BG};border-radius:5px;border:1px solid rgba(124,154,144,0.12); }}
  .tl-bar {{ position:absolute;top:3px;height:18px;border-radius:4px;display:flex;align-items:center;padding:0 6px;min-width:34px; }}
  .tl-bar span {{ font-size:9px;color:#03110d;font-weight:700;white-space:nowrap; }}
  table {{ width:100%;border-collapse:collapse;font-size:10.5px; }}
  th {{ text-align:left;color:{TEAL};font-size:9px;letter-spacing:0.5px;text-transform:uppercase;padding:8px 10px;border-bottom:1px solid {BORDER};white-space:nowrap; }}
  td {{ padding:8px 10px;border-bottom:1px solid rgba(124,154,144,0.1);white-space:nowrap; }}
  td.label-cell {{ white-space:nowrap;min-width:190px; }}
  .mono {{ font-variant-numeric:tabular-nums; }}
  .ov-grid {{ display:grid;grid-template-columns:1fr 1fr;gap:14px; }}
  .ov {{ background:{BG};border:1px solid {BORDER};border-radius:10px;padding:14px 16px; }}
  .ov-wide {{ grid-column:1 / -1; }}
  .ov-k {{ font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:{TEAL};margin-bottom:6px; }}
  .ov-v {{ font-size:12px;color:{INK};line-height:1.55; }}
  .topic {{ font-size:10px;color:{INK_MUTED};margin-bottom:12px; }}
  .stream {{ background:{BG};border:1px solid {BORDER};border-radius:8px;padding:14px;font-size:10px; }}
  .ev {{ display:flex;gap:10px;padding:3px 0;border-bottom:1px solid rgba(124,154,144,0.07); }}
  .ev-t {{ color:{INK_MUTED};width:78px;flex-shrink:0; }}
  .ev-run {{ color:{AMBER};width:120px;flex-shrink:0; }}
  .ev-name {{ width:190px;flex-shrink:0;font-weight:600; }}
  .ev-detail {{ color:{INK_MUTED}; }}
  .footer {{ margin-top:28px;padding-top:14px;border-top:1px solid {BORDER};font-size:9px;color:{INK_MUTED};display:flex;justify-content:space-between; }}
</style></head><body>
  <div class="header">
    <div class="logo"></div>
    <div>
      <div class="h-title">NgineAgent · Engine Run Report</div>
      <div class="h-sub">Metadata Validation &amp; Correction Engine — Execution Telemetry</div>
    </div>
  </div>
  <div class="pills">{status_pill}<span class="pill" style="color:{INK_MUTED}">{esc(gen)}</span>{trace_chips}<span class="pill" style="color:{INK_MUTED}">Topic: engine.events.v1</span></div>
  {body}
  <div class="footer">
    <span>NgineAgent · telemetry derived from real engine runs · no synthetic metrics</span>
    <span>Generated {esc(gen)}</span>
  </div>
</body></html>"""


async def _render_pdf(html_path: Path, pdf_path: Path):
    from playwright.async_api import async_playwright
    file_url = "file:///" + str(html_path).replace("\\", "/")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(file_url, wait_until="networkidle", timeout=30000)
        await page.pdf(path=str(pdf_path), format="A4",
                       margin={"top": "12mm", "right": "10mm", "bottom": "12mm", "left": "10mm"},
                       print_background=True)
        await browser.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", action="append", default=[], help="Run id (repeatable)")
    p.add_argument("--all", action="store_true", help="Render every run in runs/")
    p.add_argument("--out", help="Output basename (default: derived from run ids)")
    p.add_argument("--no-pdf", action="store_true", help="HTML only, skip PDF render")
    args = p.parse_args()

    run_ids = list(args.run)
    if args.all:
        run_ids = sorted(p.stem for p in RUNS_DIR.glob("*.jsonl"))
    if not run_ids:
        raise SystemExit("[ERR] specify --run <id> (repeatable) or --all")

    runs = [load_run(rid) for rid in run_ids]
    html = render_report(runs)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    base = args.out or ("_".join(run_ids) if len(run_ids) <= 2 else f"{run_ids[0]}_plus{len(run_ids)-1}")
    html_path = REPORTS_DIR / f"{base}_ENGINE-RUN-REPORT.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"  ✓ {html_path}")

    if not args.no_pdf:
        pdf_path = REPORTS_DIR / f"{base}_ENGINE-RUN-REPORT.pdf"
        try:
            import asyncio
            asyncio.run(_render_pdf(html_path, pdf_path))
            print(f"  ✓ {pdf_path}")
        except Exception as e:
            print(f"  [WARN] PDF render skipped ({type(e).__name__}: {str(e)[:80]}). HTML is ready.")

    # honest console summary
    total_steps = sum(len(r["steps"]) for r in runs)
    print(f"\n  Rendered {len(runs)} run(s), {total_steps} steps — all numbers from real event logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
