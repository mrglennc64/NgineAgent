# NgineAgent — Engine Domains

The validation/correction engine is **multi-domain**: it loads a `<domain>_schema.json`
(required fields + field patterns) and an optional `<domain>_rules.json` (penalties,
thresholds, domain logic) per request. `BaseValidator` runs schema + regex checks for
every domain; `MusicValidator` extends it with royalty-gap + statute logic.

## Domain status (honest)

| Domain | Status | Backing product | Notes |
|---|---|---|---|
| **music** | ✅ Production | HeyRoya / Kataloghub | Full: schema + rules + MusicValidator (ISRC/ISWC/IPI/splits, royalty-gap, §507(b) statute). |
| **healthcare** | ✅ Real (this repo) | Denials (RCM) | Schema modeled on the Denials app data shape — CARC/RARC codes, NPI, CPT, ICD-10, modifiers, claim amounts. Structural + format validation. Denial *reasoning/appeal* lives in the Denials app's LLM routes, not the engine. |
| **invoice** | ⚠️ Stub | — | Schema only (invoice_number, issue_date, amount, vendor_id + format checks). No domain rules yet. |
| **base** | ◻️ Fallback | — | Validates only that the file is non-empty. Default catch-all. |
| **comms / CIP** | ❌ Not built | CIP | No schema, no rules. CIP (Communications Intelligence) is comms data (channels, transcripts, messages) — a different shape from the engine's tabular/metadata model. Needs a data shape defined before a real domain can be built. The `war` repo is *web assessment*, not comms — it does not supply a CIP schema. |

## Files here

- `healthcare_schema.json` — required fields + regex patterns for denial/claim rows
- `healthcare_rules.json` — denial-recovery penalties, timely-filing thresholds, CARC category map
- (`samples/denials-sample.csv` exercises this domain)

## Deployed to the live engine (engine.usesmpt.com, `/srv/engine`)

These were installed + tested on the running engine on 2026-06-10:

1. `healthcare_schema.json` → `/srv/engine/schemas/` (replaced the stub; `.bak` kept)
2. `healthcare_rules.json` → `/srv/engine/rules/`
3. **Bugfix** — `routes_validation.py`: `/validation/worksheet` now `fillna("")` before
   `to_dict` (was throwing `ValueError: nan not JSON compliant`). `.bak` kept.
4. **Bugfix** — `base_validator.py`: pattern checks normalize pandas float-coercion
   (`1234567890.0` → `1234567890`) so numeric-looking string fields (NPI, CPT, amount)
   don't false-positive when a sibling cell is blank. `.bak` kept.

> The live engine source (`/srv/engine`) is **not yet in version control** — these
> fixes exist on the box with `.bak` backups. Recommend committing `/srv/engine` to a
> private repo so engine changes are tracked. The domain JSON here is the source of
> truth for the schema/rules and can be re-deployed from this repo.

## Verified

`POST /validation/validate` with `domain=healthcare` on `samples/denials-sample.csv`
returns 3 genuine issues (missing denial_code, missing NPI, malformed CPT) — no false
positives. `/validation/worksheet` returns HTTP 200 with blank cells as `""`.
