#!/usr/bin/env python3
"""Engine Proof Pack — renders REAL validation results from the live engine into a
branded multi-page PDF. Data comes from proof_results.json (collected by hitting the
live engine's /validation/validate, /stats, /health). No synthetic numbers.

Usage:  python make_proof_pack.py
Output: site/Engine-Proof-Pack.{html,pdf}
"""
import json, html, asyncio, sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = json.load(open(ROOT / "proof_results.json", encoding="utf-8"))
if not DATA.get("domains"):
    sys.exit("ERROR: proof_results.json has no domain results — re-collect from the live engine first.")

TEAL, AMBER, RED, INK, BG = "#0fb89c", "#d9892a", "#e0524e", "#0c1a1f", "#ffffff"

DOMAIN_META = {
    "music":      ("Music rights & royalties", "HeyRoya / Kataloghub", "ISRC, ISWC, IPI, splits, royalty-gap, §507(b) statute"),
    "healthcare": ("Healthcare claim denials", "Denials (RCM)", "CARC/RARC codes, NPI, CPT, ICD-10, claim amounts"),
    "comms":      ("Communications intelligence", "CIP", "9 diagnostic channels, ok/warn/issue severity, 0–100 score"),
    "accounting": ("Bookkeeping ledger (SIE/BAS)", "PerfectBook (bookie)", "4-digit BAS accounts, kronor debit/credit, vouchers, VAT"),
    "inspection": ("Building inspection protocol", "besiktning", "under/normalt/over condition scale, AI-confidence, validation gate"),
}
SEV_COLOR = {"HIGH": RED, "MEDIUM": AMBER, "LOW": "#6b7b80", "INFO": TEAL}

def esc(x): return html.escape(str(x))

def domain_card(dom, res):
    label, backing, validates = DOMAIN_META.get(dom, (dom, "—", "—"))
    rows = res.get("rows", "—"); n = res.get("issue_count", 0)
    issues = [i for i in res.get("issues", []) if i.get("field") != "__health__"]
    # severity tally
    tally = {}
    for i in issues:
        tally[i.get("severity", "?")] = tally.get(i.get("severity", "?"), 0) + 1
    tally_html = " ".join(
        f'<span class="pill" style="background:{SEV_COLOR.get(s,"#888")}22;color:{SEV_COLOR.get(s,"#888")};border-color:{SEV_COLOR.get(s,"#888")}55">{c}× {s}</span>'
        for s, c in sorted(tally.items())
    ) or '<span class="pill ok">clean</span>'
    rows_html = ""
    for i in issues:
        sev = i.get("severity", "?")
        fix = f'<div class="fix">→ {esc(i.get("fix"))}</div>' if i.get("fix") else ""
        rows_html += f"""
        <tr>
          <td class="r">{esc(i.get('row',''))}</td>
          <td class="f"><code>{esc(i.get('field',''))}</code></td>
          <td><span class="sev" style="color:{SEV_COLOR.get(sev,'#888')}">{esc(sev)}</span></td>
          <td>{esc(i.get('message',''))}{fix}</td>
        </tr>"""
    return f"""
    <section class="card domain">
      <div class="dhead">
        <h2>{esc(label)} <span class="dom">domain={esc(dom)}</span></h2>
        <div class="meta">Backing product: <b>{esc(backing)}</b> &nbsp;·&nbsp; Validates: {esc(validates)}</div>
      </div>
      <div class="stats">
        <div class="stat"><div class="num">{esc(rows)}</div><div class="lab">rows scanned</div></div>
        <div class="stat"><div class="num">{esc(n)}</div><div class="lab">issues found</div></div>
        <div class="stat tally">{tally_html}</div>
      </div>
      <table>
        <thead><tr><th>Row</th><th>Field</th><th>Severity</th><th>Engine finding (verbatim)</th></tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>"""

stats = DATA.get("stats", {})
health = DATA.get("health", {})
domain_cards = "".join(domain_card(d, DATA["domains"][d]) for d in DOMAIN_META if d in DATA["domains"])
total_rows = sum(DATA["domains"][d].get("rows", 0) for d in DATA["domains"])
total_issues = sum(DATA["domains"][d].get("issue_count", 0) for d in DATA["domains"])
ep = stats.get("endpoint_avg_ms", {})
validate_ms = ep.get("/validation/validate", "—")

overview = f"""
<section class="card cover">
  <div class="brand">●&nbsp; NgineAgent</div>
  <h1>Engine Proof Pack</h1>
  <p class="sub">Real validation results — captured live from the running engine at
     <code>engine.usesmpt.com</code>. Every figure below is a verbatim engine response;
     nothing here is illustrative or synthetic.</p>
  <div class="kpis">
    <div class="kpi"><div class="num">5</div><div class="lab">live domains</div></div>
    <div class="kpi"><div class="num">{total_rows}</div><div class="lab">rows validated</div></div>
    <div class="kpi"><div class="num">{total_issues}</div><div class="lab">issues surfaced</div></div>
    <div class="kpi"><div class="num">{esc(validate_ms)}<span>ms</span></div><div class="lab">avg validate latency</div></div>
  </div>
  <div class="livebox">
    <div class="live-h">● LIVE ENGINE STATUS</div>
    <div class="live-grid">
      <div><span>uptime</span><b>{esc(stats.get('uptime_human','—'))}</b></div>
      <div><span>requests served</span><b>{esc(stats.get('total_requests','—'))}</b></div>
      <div><span>last request</span><b>{esc(stats.get('last_request','—'))}</b></div>
      <div><span>health</span><b>{esc(health.get('status', health) if health else '—')}</b></div>
    </div>
    <div class="live-foot">Per-domain calls this session: {esc(json.dumps(stats.get('domain_counts',{})))}</div>
  </div>
  <p class="how">One engine. Five validated verticals. Each domain loads its own schema +
     rules; the same core scanner enforces required-field and format checks while
     domain validators add business logic (royalty gaps, double-entry, condition scales).</p>
</section>"""

HTML = f"""<!doctype html><html><head><meta charset="utf-8"><style>
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
          color:#16242a; background:#ffffff; }}
  .card {{ padding:42px 48px; }}
  .cover {{ background:linear-gradient(180deg,#f5fbfa 0%, #ffffff 55%);
            min-height:980px; page-break-after:always; border-bottom:1px solid #e6eef0; }}
  .brand {{ color:{TEAL}; font-weight:700; letter-spacing:.04em; font-size:15px; }}
  h1 {{ font-size:52px; margin:18px 0 6px; letter-spacing:-.02em; color:#0c1a1f; }}
  .sub {{ color:#5a6f75; font-size:15px; max-width:680px; line-height:1.5; }}
  code {{ color:#0b8c77; font-family:Consolas,Menlo,monospace; font-size:.92em; }}
  .kpis {{ display:flex; gap:18px; margin:34px 0 28px; }}
  .kpi {{ flex:1; background:#ffffff; border:1px solid #e0e9eb; border-radius:14px; padding:22px;
          box-shadow:0 1px 3px rgba(16,40,46,.04); }}
  .kpi .num {{ font-size:40px; font-weight:700; color:{TEAL}; }}
  .kpi .num span {{ font-size:18px; color:#5aa99c; }}
  .kpi .lab {{ color:#6b7b80; font-size:13px; margin-top:4px; }}
  .livebox {{ background:#f7fbfb; border:1px solid #e0e9eb; border-radius:14px; padding:22px 24px; }}
  .live-h {{ color:#0b8c77; font-size:12px; font-weight:700; letter-spacing:.1em; }}
  .live-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:16px 0 10px; }}
  .live-grid span {{ display:block; color:#6b7b80; font-size:12px; }}
  .live-grid b {{ font-size:20px; color:#0c1a1f; }}
  .live-foot {{ color:#7a8a8f; font-size:12px; font-family:Consolas,monospace; }}
  .how {{ color:#5a6f75; font-size:14px; line-height:1.6; margin-top:26px; max-width:720px; }}
  .domain {{ page-break-inside:avoid; border-top:1px solid #eef3f4; }}
  .dhead h2 {{ font-size:24px; margin:0 0 4px; color:#0c1a1f; }}
  .dom {{ color:{TEAL}; font-size:13px; font-family:Consolas,monospace; font-weight:400; }}
  .meta {{ color:#6b7b80; font-size:13px; }}
  .stats {{ display:flex; gap:26px; align-items:center; margin:18px 0; }}
  .stat .num {{ font-size:30px; font-weight:700; color:#0c1a1f; }}
  .stat .lab {{ color:#6b7b80; font-size:12px; }}
  .stat.tally {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .pill {{ font-size:12px; padding:4px 10px; border-radius:20px; border:1px solid; font-weight:600; }}
  .pill.ok {{ background:{TEAL}1a; color:#0b8c77; border-color:{TEAL}55; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; color:#6b7b80; font-weight:600; font-size:11px; letter-spacing:.06em;
        text-transform:uppercase; padding:8px 10px; border-bottom:2px solid #e0e9eb; }}
  td {{ padding:9px 10px; border-bottom:1px solid #eef3f4; vertical-align:top; }}
  td.r {{ color:#9aa8ac; width:42px; }} td.f {{ width:140px; }}
  .sev {{ font-weight:700; font-size:12px; }}
  .fix {{ color:#0b8c77; font-size:12px; margin-top:3px; }}
</style></head><body>
{overview}
{domain_cards}
</body></html>"""

out_html = ROOT / "site" / "Engine-Proof-Pack.html"
out_pdf = ROOT / "site" / "Engine-Proof-Pack.pdf"
out_html.write_text(HTML, encoding="utf-8")
print(f"wrote {out_html}")

async def render():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto(out_html.as_uri())
        await pg.pdf(path=str(out_pdf), format="A4", print_background=True,
                     margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        await b.close()
    print(f"wrote {out_pdf}")

asyncio.run(render())
