# NgineAgent — N8N Workflow Exports

Three importable N8N workflows that drive the NgineAgent validation/correction
engine through its HTTP API. They give you (and a prospective buyer) a visual,
drag-and-drop orchestration layer over the engine — proving it's API-driven and
integration-ready, not a one-off script.

| File | Trigger | What it does |
|---|---|---|
| `n8n_metadata_validation.json` | POST webhook (catalog upload) | Scans a catalog, returns issues + CWR health score |
| `n8n_cip_correction.json` | POST webhook (catalog + worksheet) | Applies publisher decisions, returns cleaned CSV + after-score |
| `n8n_dip_intake.json` | POST webhook (intake) | Validates, branches on score (≥80 auto-accept, else route to correction) |

## Import

1. In N8N: **Workflows → Import from File** → pick one of the `.json` files.
2. Set two environment variables on your N8N instance (Settings → Variables, or
   the `.env` of a self-hosted instance):
   - `NGINE_ENGINE_URL` — base URL of the live engine, e.g. `https://engine.usesmpt.com`
   - `NGINE_BASIC_AUTH` — base64 of `user:password` for the engine's HTTP Basic Auth.
     Generate with: `echo -n 'Glenn:YOUR_PASSWORD' | base64`
3. Activate the workflow. The webhook URL N8N gives you is your endpoint.

## Engine endpoints these call

These are the **live** FastAPI routes on `engine.usesmpt.com` (Generic
Validation/Correction Engine v0.1.0), all `multipart/form-data`, synchronous:

- `POST /validation/validate` — field `file` (+ optional `domain`) → issues + score
- `POST /validation/worksheet` — field `file` → correction worksheet CSV
- `POST /correction/apply` — fields `original_file` + `worksheet_file` → cleaned CSV
- `POST /export/file` — field `corrected_file` (+ optional `fmt`)
- `GET  /health` · `GET /stats` · `GET /docs` (Swagger UI)

Auth is HTTP Basic (user `Glenn`). The engine is fast and responds synchronously
— no job-polling needed.

## Hosting

- **Self-hosted (free):** `docker run -it --rm -p 5678:5678 n8nio/n8n` — workflows + data stay on your box.
- **N8N Cloud:** ~€20-50/mo, no infra to run.

## Note on the polling pattern

The exports use a fixed `Wait` (3s) before reading job status for simplicity.
For production, replace the single Wait with a poll-loop (IF job.status !=
"done" → Wait → re-GET) or have the engine call an N8N webhook on completion.
