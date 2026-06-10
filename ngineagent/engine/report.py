from __future__ import annotations

from .detect import ScanResult
from .score import classify_tone


def render_health_report(scan: ScanResult, scan_id: str, scan_date: str) -> str:
    """Render the Metadata Health Report as standalone HTML.

    Mirrors §6 of internal-tools-spec.md and the buildHealthReport() in
    scan-catalog.html. Returns HTML; caller is responsible for PDF conversion
    (WeasyPrint / Playwright).
    """
    titles = scan.titles
    issues = scan.issues
    blocking = scan.blocking
    resolvable = scan.resolvable
    score = scan.score
    total_contribs = scan.total_contribs
    total = len(issues)

    tone = classify_tone(score)
    if tone == "good":
        hero_bg = "linear-gradient(135deg, #0d3a2a 0%, #0f5d3f 100%)"
        hero_border = "#1f7a4a"
        hero_accent = "#86efac"
        tag_bg = "rgba(29,212,183,0.18)"
        tag_color = "#1dd4b7"
        section_color = "#1dd4b7"
        score_color = "#1dd4b7"
        tag_text = "✓ Pre-cleaning scan"
        hero_h1 = "Catalog largely CWR-ready"
    elif tone == "warn":
        hero_bg = "linear-gradient(135deg, #3a2810 0%, #5d4220 100%)"
        hero_border = "#7a5a30"
        hero_accent = "#fbbf77"
        tag_bg = "rgba(248,113,113,0.18)"
        tag_color = "#f2b36a"
        section_color = "#f2b36a"
        score_color = "#f2b36a"
        tag_text = "⚠ Before cleaning"
        hero_h1 = "Resolvable issues identified"
    else:
        hero_bg = "linear-gradient(135deg, #2a1810 0%, #4a2820 100%)"
        hero_border = "#6b3a30"
        hero_accent = "#fbbf77"
        tag_bg = "rgba(248,113,113,0.18)"
        tag_color = "#f87171"
        section_color = "#f87171"
        score_color = "#f87171"
        tag_text = "⚠ Before cleaning"
        hero_h1 = "Major Fixes Required — Catalog Not CWR-Ready"

    by_work: dict[str, list] = {}
    for i in issues:
        by_work.setdefault(i.work, []).append(i)

    by_field: dict[str, list] = {}
    for i in issues:
        by_field.setdefault(i.field, []).append(i)

    field_label = {
        "iswc": "Missing ISWC",
        "isrc": "Missing ISRC",
        "split_total": "Incorrect split sums",
        "writer_ipi": "Missing writer IPI",
        "society": "Missing society",
        "foreign_writer": "Foreign writer — no agreement declared",
        "role": "Invalid role",
        "writer_name": "Writer name variants",
    }

    def issue_short(i) -> str:
        f = i.field
        if f == "split_total":
            return f"splits {i.current}"
        if f == "iswc":
            return "missing ISWC"
        if f == "isrc":
            return "missing ISRC"
        if f == "writer_ipi":
            return "missing IPI"
        if f == "society":
            return "missing society"
        if f == "foreign_writer":
            return "no E/SE/AM declaration"
        if f == "role":
            return "invalid role"
        if f == "writer_name":
            return "name variant"
        return f

    def esc(s: object) -> str:
        return (
            ("" if s is None else str(s))
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    work_rows_html = "".join(
        f'<tr><td class="title">{esc(t)}</td>'
        f'<td><span class="pill {"clean" if not by_work.get(t) else "major"}">'
        f'{"Clean" if not by_work.get(t) else "Major fixes"}</span></td>'
        f'<td>{esc(", ".join(issue_short(i) for i in by_work.get(t, [])) or "—")}</td>'
        f"</tr>"
        for t in titles
    )

    most_common_items = sorted(by_field.items(), key=lambda kv: -len(kv[1]))[:8]
    most_common_html = "".join(
        f"<li><strong>{esc(field_label.get(f, f))}:</strong> "
        f"{len(lst)} {'work' if len(lst) == 1 else 'works'}</li>"
        for f, lst in most_common_items
    )
    if not most_common_html:
        most_common_html = '<li class="green">No issues detected — catalog is in good shape.</li>'

    iswc_missing = len(by_field.get("iswc", []))
    iswc_covered = len(titles) - iswc_missing
    isrc_missing = len(by_field.get("isrc", []))
    isrc_covered = len(titles) - isrc_missing

    split_html = "".join(
        f"<li>{esc(i.work)} → <strong>{esc(i.current)}</strong></li>"
        for i in by_field.get("split_total", [])
    )
    ipi_html = "".join(
        f"<li>{esc(i.current)}</li>" for i in by_field.get("writer_ipi", [])
    )
    society_html = "".join(
        f'<li class="amber">{esc(i.current)}</li>' for i in by_field.get("society", [])
    )
    role_html = "".join(
        f"<li>{esc(i.current)} → not CWR-valid</li>" for i in by_field.get("role", [])
    )
    name_html = "".join(
        f'<li class="amber">"{esc(i.current)}" → {esc(i.suggested)}</li>'
        for i in by_field.get("writer_name", [])
    )
    foreign_html = "".join(
        f"<li>{esc(i.current)} → STIM will reject packet</li>"
        for i in by_field.get("foreign_writer", [])
    )

    section_n = 1
    s_summary = section_n
    section_n += 1
    s_coverage = section_n
    section_n += 1
    s_split = None
    if split_html:
        s_split = section_n
        section_n += 1
    s_role_writer = None
    if role_html or name_html or foreign_html:
        s_role_writer = section_n
        section_n += 1
    s_per_work = section_n

    split_section = (
        f'<div class="section"><h2>{s_split}. Share validation</h2>'
        f'<p class="lede">Incorrect split sums (blocking):</p>'
        f'<div class="panel"><ul>{split_html}</ul>'
        f'<p class="impact-note">Impact: these works cannot be submitted to STIM/ICE until splits equal exactly 100%.</p>'
        f"</div></div>"
        if split_html
        else ""
    )

    role_writer_section = ""
    if role_html or name_html or foreign_html:
        parts = []
        if role_html:
            parts.append(f'<div class="group-h">Invalid role</div><ul>{role_html}</ul>')
        if name_html:
            parts.append(f'<div class="group-h">Name variants</div><ul>{name_html}</ul>')
        if foreign_html:
            parts.append(
                f'<div class="group-h">Foreign writer with no agreement</div><ul>{foreign_html}</ul>'
            )
        role_writer_section = (
            f'<div class="section"><h2>{s_role_writer}. Role &amp; writer validation</h2>'
            f'<div class="panel">{"".join(parts)}</div></div>'
        )

    iswc_extra = (
        f"<li>{iswc_missing} {'work' if iswc_missing == 1 else 'works'} flagged as &quot;Unregistered Work — No ISWC found&quot;</li>"
        if iswc_missing > 0
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Metadata Health Report (Before Cleaning) — HeyRoya</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ background:#05070b; color:#f5f7fb; font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; line-height:1.55; padding:32px 20px 64px; }}
.container {{ max-width:1080px; margin:0 auto; }}
h1, h2, h3 {{ font-weight:600; }}
header.topnav {{ display:flex; align-items:center; justify-content:space-between; padding:0 0 24px; flex-wrap:wrap; gap:1rem; border-bottom:1px solid rgba(27,34,51,0.8); margin-bottom:28px; }}
.brand {{ display:flex; align-items:center; gap:0.65rem; font-weight:700; color:#1dd4b7; }}
.meta {{ font-size:12px; color:#8f9bb3; text-align:right; }}
.hero {{ background:{hero_bg}; border:1px solid {hero_border}; border-radius:18px; padding:28px 32px; margin-bottom:24px; display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:24px; }}
.hero-left h1 {{ font-size:24px; font-weight:800; margin-bottom:6px; color:#fff; }}
.hero-left p {{ color:{hero_accent}; font-size:14px; }}
.pre-tag {{ display:inline-block; background:{tag_bg}; color:{tag_color}; border:1px solid {tag_color}; border-radius:999px; padding:3px 12px; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:10px; }}
.score-circle {{ width:100px; height:100px; border-radius:999px; background:rgba(0,0,0,0.3); border:4px solid {score_color}; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
.score-num {{ font-size:32px; font-weight:800; color:{score_color}; line-height:1; }}
.score-label {{ font-size:10px; color:{hero_accent}; margin-top:4px; text-transform:uppercase; letter-spacing:0.06em; }}
.summary-row {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-bottom:24px; }}
.summary-card {{ background:#0b0f18; border:1px solid #1b2233; border-radius:12px; padding:16px 18px; }}
.summary-card .label {{ font-size:11px; color:#8f9bb3; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px; }}
.summary-card .value {{ font-size:26px; font-weight:700; color:#f5f7fb; }}
.summary-card .sub {{ font-size:12px; color:#c3cad8; margin-top:2px; }}
.summary-card.red .value {{ color:#f87171; }}
.summary-card.amber .value {{ color:#f2b36a; }}
.summary-card.gray .value {{ color:#8f9bb3; }}
.section {{ margin-bottom:28px; }}
.section h2 {{ font-size:14px; font-weight:700; color:{section_color}; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:10px; }}
.section .lede {{ color:#c3cad8; font-size:14px; margin-bottom:12px; }}
.panel {{ background:#0b0f18; border:1px solid #1b2233; border-radius:12px; padding:18px 22px; }}
.panel ul {{ list-style:none; padding:0; margin:0; }}
.panel li {{ color:#c3cad8; font-size:14px; padding:6px 0 6px 24px; position:relative; }}
.panel li::before {{ content:'✕'; color:#f87171; font-weight:700; position:absolute; left:0; }}
.panel li.amber::before {{ content:'!'; color:#f2b36a; }}
.panel li.green::before {{ content:'✓'; color:#1dd4b7; }}
.panel li strong {{ color:#f5f7fb; }}
.panel .group-h {{ font-weight:700; color:#f5f7fb; margin-top:12px; margin-bottom:6px; font-size:13px; }}
.panel .group-h:first-child {{ margin-top:0; }}
.impact-note {{ color:#fbbf77; font-size:13px; margin-top:12px; padding-top:10px; border-top:1px solid rgba(242,179,106,0.2); font-style:italic; }}
.works-table {{ background:#0b0f18; border:1px solid #1b2233; border-radius:12px; overflow:hidden; }}
.works-table table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.works-table th {{ text-align:left; padding:12px 16px; font-size:11px; color:#8f9bb3; text-transform:uppercase; letter-spacing:0.06em; font-weight:700; background:#0a0d14; border-bottom:1px solid #1b2233; }}
.works-table td {{ padding:12px 16px; border-bottom:1px solid #1b2233; color:#c3cad8; vertical-align:top; }}
.works-table tr:last-child td {{ border-bottom:0; }}
.works-table .title {{ color:#f5f7fb; font-weight:500; }}
.pill {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:11px; font-weight:700; letter-spacing:0.04em; text-transform:uppercase; white-space:nowrap; }}
.pill.major {{ background:rgba(248,113,113,0.12); color:#f87171; border:1px solid rgba(248,113,113,0.4); }}
.pill.clean {{ background:rgba(29,212,183,0.12); color:#1dd4b7; border:1px solid rgba(29,212,183,0.4); }}
.disclaimer {{ background:#0b0f18; border:1px solid #1b2233; border-radius:12px; padding:18px 22px; margin-top:16px; }}
.disclaimer .label {{ font-size:12px; font-weight:700; color:#1dd4b7; text-transform:uppercase; letter-spacing:0.08em; margin-bottom:6px; }}
.disclaimer p {{ color:#c3cad8; font-size:13px; margin:0; }}
@media print {{
  body {{ background:#fff; color:#000; padding:20px; }}
  header.topnav {{ display:none; }}
  .hero, .panel, .summary-card, .works-table, .disclaimer {{ background:#fff !important; border:1px solid #ccc !important; color:#000 !important; }}
  .hero-left h1, .summary-card .value, .panel li strong, .panel .group-h, .works-table .title {{ color:#000 !important; }}
  .hero-left p, .summary-card .label, .summary-card .sub, .panel li, .works-table td, .works-table th, .disclaimer p {{ color:#444 !important; }}
  .score-circle {{ background:#fff !important; }}
  .pre-tag {{ background:#fff !important; }}
}}
</style>
</head>
<body>
<div class="container">

  <header class="topnav">
    <div class="brand">HeyRoya · Metadata Health Report</div>
    <div>
      <div class="meta">Catalog: {len(titles)} works · {total_contribs} contributor entries</div>
      <div class="meta">Scan ID: {esc(scan_id)} · Generated {esc(scan_date)}</div>
    </div>
  </header>

  <div class="hero">
    <div class="hero-left">
      <span class="pre-tag">{tag_text}</span>
      <h1>{hero_h1}</h1>
      <p>{len(titles)} works analyzed · {total} {"issue" if total == 1 else "issues"} detected · {blocking} blocking · {resolvable} resolvable · pre-cleaning diagnostic.</p>
    </div>
    <div class="score-circle">
      <div class="score-num">{score}</div>
      <div class="score-label">/ 100</div>
    </div>
  </div>

  <div class="summary-row">
    <div class="summary-card gray"><div class="label">Works analyzed</div><div class="value">{len(titles)}</div><div class="sub">{total_contribs} contributor entries</div></div>
    <div class="summary-card gray"><div class="label">Total issues</div><div class="value">{total}</div><div class="sub">across the catalog</div></div>
    <div class="summary-card red"><div class="label">Blocking</div><div class="value">{blocking}</div><div class="sub">prevent CWR submission</div></div>
    <div class="summary-card amber"><div class="label">Resolvable</div><div class="value">{resolvable}</div><div class="sub">fixable with confirmation</div></div>
  </div>

  <div class="section">
    <h2>{s_summary}. High-level summary</h2>
    <p class="lede">Pre-cleaning diagnostic. No assumptions, no auto-fixes. Every correction will require publisher confirmation.</p>
    <div class="panel">
      <div class="group-h">Most common problems</div>
      <ul>{most_common_html}</ul>
    </div>
  </div>

  <div class="section">
    <h2>{s_coverage}. Identifier coverage</h2>
    <div class="panel">
      <div class="group-h">ISWC</div>
      <ul>
        <li class="{'green' if iswc_missing == 0 else 'amber'}">{iswc_covered} / {len(titles)} works have a valid ISWC</li>
        {iswc_extra}
      </ul>
      <div class="group-h">ISRC</div>
      <ul>
        <li class="{'green' if isrc_missing == 0 else 'amber'}">{isrc_covered} / {len(titles)} works have a valid ISRC</li>
      </ul>
      {f'<div class="group-h">IPI</div><ul>{ipi_html}</ul>' if ipi_html else ''}
      {f'<div class="group-h">Society</div><ul>{society_html}</ul>' if society_html else ''}
    </div>
  </div>

  {split_section}

  {role_writer_section}

  <div class="section">
    <h2>{s_per_work}. Per-work status</h2>
    <div class="works-table">
      <table>
        <thead><tr><th>Work</th><th>Status</th><th>Key issues</th></tr></thead>
        <tbody>{work_rows_html}</tbody>
      </table>
    </div>
  </div>

  <div class="disclaimer">
    <div class="label">Publisher Confirmation Required</div>
    <p>External metadata sources are used only to validate identifiers. All final decisions and catalog updates rest with the publisher.</p>
  </div>

  <p style="font-size:11px;color:#8f9bb3;text-align:center;margin-top:24px;">
    HeyRoya · Metadata compliance for Nordic music publishers · ken@heyroya.se
  </p>

</div>
</body>
</html>"""
