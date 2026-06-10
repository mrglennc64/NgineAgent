# NgineAgent

**The operator + telemetry layer for the metadata validation & correction engine** that powers CIP, DIP, HeyRoya, and Kataloghub.

NgineAgent wraps the engine in an instrumented run-harness that emits a structured event stream, then renders an **Engine Run Report** — execution timeline, step-level telemetry, event log, and performance metrics — from **real runs on real catalogs**. It turns an invisible engine into an observable, measurable platform.

> Every number in every report is computed from a real engine run. There are no synthetic or demo metrics anywhere in this repo — if a run log is missing or empty, the report generator errors out rather than render placeholders.

---

## What's inside

```
ngineagent/
  engine/            # the real validation/correction engine (pure Python, no infra)
    detect.py        #   detect_issues(catalog) -> ScanResult  (8 CWR issue types + health score)
    apply.py         #   apply_decisions(catalog, worksheet) -> cleaned CSV
    report.py        #   render_health_report(scan) -> branded HTML
    score.py csv_io.py constants.py worksheet.py
  engine_run.py      # instrumented run-wrapper → emits engine.events.v1 JSONL telemetry
  run_report.py      # reads the telemetry → renders Engine Run Report (HTML + PDF)
  n8n/               # importable N8N workflows that drive the engine via its HTTP API
samples/             # real catalog fixtures to run against
runs/                # event logs (engine.events.v1 JSONL) — generated
reports/             # rendered health reports + run reports — generated
```

## Quick start

```bash
# 1. (optional) install Playwright for PDF output — HTML works without it
pip install -r requirements.txt && python -m playwright install chromium

# 2. Run the engine on a real catalog (validation)
python -m ngineagent.engine_run --catalog samples/test-15-mixed.csv --run-id RUN-VAL

# 3. Run a correction pass (before/after health score)
python -m ngineagent.engine_run \
    --catalog samples/test-15-mixed.csv \
    --corrections samples/corrections-worksheet-test-15-filled.csv \
    --run-id RUN-CORR

# 4. Render the Engine Run Report from the real telemetry
python -m ngineagent.run_report --run RUN-VAL --run RUN-CORR
# → reports/RUN-VAL_RUN-CORR_ENGINE-RUN-REPORT.{html,pdf}
```

On the bundled 15-work sample the correction pass takes the catalog from a CWR
health score of **53 → 88** — a real, reproducible before/after you can show.

## The event stream (`engine.events.v1`)

`engine_run.py` emits append-only JSONL telemetry per run:

```
engine.run.started → engine.step.started → engine.step.completed → engine.run.completed
```

Each `engine.step.completed` carries the real measured `duration_ms`, declared
`timeout_ms`, `retries`, `status`, and step-specific metrics (issues found,
score, score delta, decisions applied). This is the "event stream" that makes
the engine observable — implemented as a JSONL log, not Kafka, which is the
right scale for this workload. (If true distributed durability is ever required,
Temporal is the migration path — deliberately not pre-built.)

## The Engine Run Report (5 sections)

1. **Executive Summary** — per-run cards + aggregate metrics
2. **Workflow Execution Timeline** — Gantt bars proportional to real step durations
3. **Step Execution Details** — full step table (duration vs. timeout, retries, status)
4. **Event Stream** — the raw `engine.events.v1` log
5. **Performance Metrics** — events/sec, retry rate, success rate, mean/p99 step duration

## N8N orchestration

See [`ngineagent/n8n/README.md`](ngineagent/n8n/README.md) — three importable
workflows (validation, CIP correction, DIP intake/routing) that drive the engine
through its HTTP API, giving a visual drag-and-drop layer over the same engine.

## Engine: what it validates

8 CWR-readiness issue types: split totals ≠ 100%, missing ISWC/ISRC, missing
writer IPI, missing society, foreign-writer declarations, invalid role codes,
and writer-name variants. Each is classed **blocking** (prevents CWR submission)
or **resolvable**. Health score = `100 − 6·blocking − 1·resolvable`.
