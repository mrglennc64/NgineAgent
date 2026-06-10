from __future__ import annotations

import re
from dataclasses import dataclass, field

from .csv_io import csv_escape, parse_csv


@dataclass
class Decision:
    id: str
    work: str
    field: str
    decision: str
    applied: str


@dataclass
class ApplyResult:
    cleaned_csv: str
    log: list[Decision] = field(default_factory=list)
    accept: int = 0
    reject: int = 0
    edit: int = 0


_SLASH_SPLIT_RE = re.compile(r"\d+\s*/\s*\d+")
_ISWC_RE = re.compile(r"T-[\d.]+-\d")
_ROLE_RE = re.compile(r"[A-Z]{1,2}")
_SOCIETY_RE = re.compile(r"\b[A-Z]{2,5}\b")
_HAS_NO_IPI_RE = re.compile(r"has no IPI.*", re.IGNORECASE)
_TRAILING_PAREN_RE = re.compile(r"\s*\(.*\)\s*$")


def _column_index(header_row: list[str], name: str) -> int:
    h = [c.strip().lower() for c in header_row]
    return h.index(name) if name in h else -1


def apply_decisions(catalog_text: str, worksheet_text: str) -> ApplyResult:
    cat_rows = parse_csv(catalog_text)
    corr_rows = parse_csv(worksheet_text)
    if len(cat_rows) < 2 or len(corr_rows) < 2:
        raise ValueError("Both files must have a header + at least 1 row.")

    cat_header = cat_rows[0]
    corr_header = corr_rows[0]

    title_idx = _column_index(cat_header, "title")
    name_idx = _column_index(cat_header, "name")
    share_idx = _column_index(cat_header, "share_percent")
    iswc_idx = _column_index(cat_header, "iswc")
    role_idx = _column_index(cat_header, "role")
    ipi_idx = _column_index(cat_header, "ipi")
    society_idx = _column_index(cat_header, "society")
    if title_idx < 0 or name_idx < 0:
        raise ValueError("Catalog must have title + name columns.")

    dec_idx = _column_index(corr_header, "decision")
    field_idx = _column_index(corr_header, "field")
    work_idx = _column_index(corr_header, "work")
    sug_idx = _column_index(corr_header, "suggested")
    pub_val_idx = _column_index(corr_header, "publisher_value")
    issue_id_idx = _column_index(corr_header, "issue_id")
    current_value_idx = 3  # mirrors the live JS's hardcoded c[3]

    works_by_title: dict[str, list[list[str]]] = {}
    for row in cat_rows[1:]:
        t = (row[title_idx] if title_idx < len(row) else "").strip()
        if not t:
            continue
        works_by_title.setdefault(t, []).append(row)

    def cell(row: list[str], idx: int) -> str:
        if idx < 0 or idx >= len(row):
            return ""
        return (row[idx] or "").strip()

    log: list[Decision] = []
    accept = reject = edit = 0

    for c in corr_rows[1:]:
        issue_id = cell(c, issue_id_idx)
        work = cell(c, work_idx)
        field_v = cell(c, field_idx).lower()
        decision = cell(c, dec_idx).lower()
        suggested = cell(c, sug_idx)
        pub_val = cell(c, pub_val_idx)
        if not work or not decision:
            continue

        rows = works_by_title.get(work)
        applied = ""

        if decision == "reject":
            reject += 1
            applied = "— kept original —"
        elif rows:
            if field_v == "split_total":
                if decision == "edit" and _SLASH_SPLIT_RE.search(pub_val):
                    parts = [float(p.strip()) for p in pub_val.split("/")]
                    for j in range(min(len(rows), len(parts))):
                        if share_idx >= 0:
                            _set(rows[j], share_idx, str(parts[j]))
                    applied = pub_val + "%"
                    edit += 1
                else:
                    each = f"{100 / len(rows):.2f}"
                    for row in rows:
                        if share_idx >= 0:
                            _set(row, share_idx, each)
                    applied = f"{each}% × {len(rows)}"
                    accept += 1

            elif field_v == "iswc":
                if decision == "edit":
                    val = pub_val
                else:
                    m = _ISWC_RE.search(suggested)
                    val = m.group(0) if m else ""
                if iswc_idx >= 0 and val:
                    for row in rows:
                        _set(row, iswc_idx, val)
                applied = val or suggested
                if decision == "edit":
                    edit += 1
                else:
                    accept += 1

            elif field_v == "writer_name":
                if decision == "edit":
                    val = pub_val
                else:
                    val = _TRAILING_PAREN_RE.sub("", suggested).strip()
                if name_idx >= 0 and val:
                    target = cell(c, current_value_idx).lower()
                    for row in rows:
                        existing = (row[name_idx] if name_idx < len(row) else "").strip().lower()
                        if existing == target:
                            _set(row, name_idx, val)
                applied = val
                if decision == "edit":
                    edit += 1
                else:
                    accept += 1

            elif field_v == "role":
                if decision == "edit":
                    val = pub_val
                else:
                    m = _ROLE_RE.search(suggested)
                    val = m.group(0) if m else "CA"
                if role_idx >= 0:
                    for row in rows:
                        _set(row, role_idx, val)
                applied = val
                if decision == "edit":
                    edit += 1
                else:
                    accept += 1

            elif field_v in ("writer_ipi", "ipi"):
                val = pub_val if decision == "edit" else ""
                if val and ipi_idx >= 0:
                    raw = cell(c, current_value_idx)
                    writer = _HAS_NO_IPI_RE.sub("", raw).strip().lower()
                    first_token = writer.split(" ")[0] if writer else ""
                    if first_token:
                        for row in rows:
                            existing = (row[name_idx] if name_idx < len(row) else "").lower()
                            if first_token in existing:
                                _set(row, ipi_idx, val)
                applied = val or "(awaiting writer)"
                if decision == "edit":
                    edit += 1
                else:
                    accept += 1

            elif field_v == "society":
                if decision == "edit":
                    val = pub_val
                else:
                    m = _SOCIETY_RE.search(suggested)
                    val = m.group(0) if m else "STIM"
                if society_idx >= 0 and val:
                    raw = cell(c, current_value_idx)
                    writer = raw.split("—")[0].strip().lower()
                    first_token = writer.split(" ")[0] if writer else ""
                    if first_token:
                        for row in rows:
                            existing = (row[name_idx] if name_idx < len(row) else "").lower()
                            if first_token in existing:
                                _set(row, society_idx, val)
                applied = val
                if decision == "edit":
                    edit += 1
                else:
                    accept += 1

            elif field_v == "foreign_writer":
                applied = "E declaration noted"
                accept += 1

            else:
                applied = f'(no merge rule for field "{field_v}")'
        else:
            applied = "(work not found in catalog)"

        log.append(
            Decision(
                id=issue_id,
                work=work,
                field=field_v,
                decision=decision,
                applied=applied,
            )
        )

    cleaned_lines = [",".join(cat_rows[0])]
    for row in cat_rows[1:]:
        cleaned_lines.append(",".join(csv_escape(v) for v in row))
    cleaned = "\n".join(cleaned_lines)

    return ApplyResult(
        cleaned_csv=cleaned,
        log=log,
        accept=accept,
        reject=reject,
        edit=edit,
    )


def _set(row: list[str], idx: int, value: str) -> None:
    while len(row) <= idx:
        row.append("")
    row[idx] = value
