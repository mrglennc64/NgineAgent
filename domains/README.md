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
| **comms / CIP** | ✅ Real (this repo) | CIP | Schema modeled on the CIP app's `Run`/`Job`/`Finding`/`Channel` types — 9 diagnostic channels (audit, seo, funnel, email, deliverability, social, browser, inventory, ivr), `ok/warn/issue` severity, 0-100 score. One row = one channel finding. Scan execution + scoring live in the CIP app; the engine validates the finding rows. |
| **accounting** | ✅ Real (this repo) | PerfectBook (bookie) | SIE/BAS double-entry ledger rows — 4-digit BAS account, kronor amount (signed debit/credit), voucher series/number/date, VAT codes. `samples/accounting-sample.csv`. |
| **inspection** | ✅ Real (this repo) | besiktning | Building-inspection protocol findings — `under_normalt/normalt/over_normalt` condition, notering id, inspector, inspection date, AI-confidence + validation gate. `samples/inspection-sample.csv`. |
| **invoice** | ⚠️ Stub | — | Schema only (invoice_number, issue_date, amount, vendor_id + format checks). No domain rules yet. |
| **base** | ◻️ Fallback | — | Validates only that the file is non-empty. Default catch-all. |

## Deliberately NOT domains (app-layer, not validation domains)

A repo becomes an engine domain only if it has a distinct **row/record data shape** to
validate. These were assessed and excluded to avoid domain sprawl/overlap:

- **digital-handshake** — split sheets (already the *music* domain's shape: contributors +
  shares to 100%) + Letters of Direction. It's a signature/authorization flow, not a new
  validation domain.
- **traplawpro** — SoundExchange claim filing. The legal/consumption layer that *uses*
  rights data and produces documents; not a distinct domain.

These belong in the **"applications built on the platform"** story, not the engine-domains
list. Five distinct verticals (music, healthcare, comms, accounting, inspection) is a
stronger, more honest pitch than seven with overlap.

## Files here

- `healthcare_schema.json` / `healthcare_rules.json` — denial/claim rows (Denials app shape). `samples/denials-sample.csv` exercises it.
- `comms_schema.json` / `comms_rules.json` — CIP scan-finding rows (CIP app shape). `samples/cip-scan-sample.csv` exercises it.
- All four JSON files are the source of truth, deployed to the live engine and tracked in the `srv-engine` repo.

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
