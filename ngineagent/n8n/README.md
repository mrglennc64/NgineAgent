# NgineAgent — N8N Workflow Exports

Three importable N8N workflows that drive the NgineAgent validation/correction
engine through its HTTP API. They give you (and a prospective buyer) a visual,
drag-and-drop orchestration layer over the engine — proving it's API-driven and
integration-ready, not a one-off script.

| File | Trigger | What it does |
|---|---|---|
| `n8n_metadata_validation.json` | POST webhook (catalog upload) | Scans a catalog, returns CWR health score + report URL |
| `n8n_cip_correction.json` | POST webhook (catalog + worksheet) | Scans, applies publisher decisions, returns cleaned CSV + after-score |
| `n8n_dip_intake.json` | POST webhook (intake) | Validates, branches on score (≥80 auto-accept, else route to correction) |

## Import

1. In N8N: **Workflows → Import from File** → pick one of the `.json` files.
2. Set two environment variables on your N8N instance (Settings → Variables, or
   the `.env` of a self-hosted instance):
   - `NGINE_ENGINE_URL` — base URL of your running engine API (e.g. `https://engine.heyroya.se`)
   - `NGINE_API_TOKEN` — bearer token for the engine API
3. Activate the workflow. The webhook URL N8N gives you is your endpoint.

## Engine endpoints these call

These map to the real FastAPI routes in the engine (`app/api/catalog.py`,
`app/api/corrections.py`, `app/api/jobs.py`):

- `POST /api/upload/catalog` — queue a catalog scan
- `POST /api/upload/corrections` — apply a decision worksheet
- `GET  /api/jobs/{job_id}` — poll job status / fetch result

## Hosting

- **Self-hosted (free):** `docker run -it --rm -p 5678:5678 n8nio/n8n` — workflows + data stay on your box.
- **N8N Cloud:** ~€20-50/mo, no infra to run.

## Note on the polling pattern

The exports use a fixed `Wait` (3s) before reading job status for simplicity.
For production, replace the single Wait with a poll-loop (IF job.status !=
"done" → Wait → re-GET) or have the engine call an N8N webhook on completion.
