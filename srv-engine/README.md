# Generic Validation/Correction Engine

A standalone, schema-driven backend engine that validates uploaded datasets, generates correction worksheets, applies corrections, and exports the result. No UI. FastAPI on the wire.

The engine is intended to live at `/srv/engine/` on the VPS, bound to `127.0.0.1:8085`, and to be reachable only over SSH or local reverse proxy. Nothing else on the host is touched.

## Pipeline

```
upload → validate → worksheet → correct → export
```

Each stage is exposed as a FastAPI endpoint and as an importable Python service.

## Endpoints

| Method | Path                   | Purpose                                                              |
| ------ | ---------------------- | -------------------------------------------------------------------- |
| POST   | `/validation/validate` | Upload a file; receive structured issues.                            |
| POST   | `/validation/worksheet`| Upload a file; receive a prioritized worksheet of issues to correct. |
| POST   | `/correction/apply`    | Upload original + worksheet; receive a corrected DataFrame preview.  |
| POST   | `/export/file`         | Upload a corrected file; download as CSV or XLSX.                    |
| GET    | `/health`              | Liveness probe.                                                      |

All upload endpoints accept `domain` as a form field: `music`, `healthcare`, `invoice`, `payroll`, or `base`.

## Domains

A domain is a `*_schema.json` (+ optional `*_rules.json`) pair under `schemas/` and `rules/`. To add a new vertical:

1. Drop `schemas/<name>_schema.json` with `required`, `fields`, etc.
2. (Optional) Drop `rules/<name>_rules.json`.
3. (Optional) Add `core/validators/<name>_validator.py` extending `BaseValidator` for domain-specific logic.
4. Wire it up in `services/validate.py :: get_validator`.

The `music` domain is the reference implementation. Its logic is ported from TrapRoyaltiesPro and lives in `core/validators/music_validator.py`.

## Music-domain provenance

Each music-specific module declares its source at the top of the file:

- `core/utils/health_score.py` — from `traproyalties-new1/api/utils/musicbrainz_audit.py`
- `core/utils/statute.py` — from `traproyalties-new1/api/services/forensic_pipeline.py :: _check_statute`
- `core/validators/music_validator.py` — penalty rubric from `musicbrainz_audit.py`, gap detection from `forensic_pipeline.py :: _detect_gaps`
- `core/worksheet/generator.py` — priority math from `cleanup_recommendations_with_shazam.py`
- `core/correctors/music_corrector.py` — apply pattern from `contract_parser.py :: apply_to_isrcs`
- `core/exporters/ddex_exporter.py` — from `traproyalties-new1/api/ddex/generator.py` + `validator.py`

All network calls (MusicBrainz, ListenBrainz, Discogs, Shazam) were stripped. The engine validates only what is in the uploaded file.

## Local development

```powershell
cd c:\Users\carin\OneDrive\Dokument\SRVengine\engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8085 --reload
```

Open http://127.0.0.1:8085/docs for the Swagger UI.

## VPS deployment

```bash
ssh root@187.77.111.16
cd /srv/engine
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --host 127.0.0.1 --port 8085
```

Bind to `127.0.0.1` so the engine is reachable only over the loopback interface. To reach it from a laptop, use an SSH tunnel: `ssh -L 8085:127.0.0.1:8085 root@187.77.111.16`.

For auto-start, install `/etc/systemd/system/engine.service` (see the deploy plan in this repo).

## Test it

```bash
curl -s -X POST http://127.0.0.1:8085/validation/worksheet \
  -F "file=@sample.csv" \
  -F "domain=music"
```
