from __future__ import annotations

import re


def parse_csv(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    text = text.replace("\r\n", "\n")
    for line in text.split("\n"):
        if not line.strip():
            continue
        cells: list[str] = []
        cur = ""
        in_q = False
        i = 0
        n = len(line)
        while i < n:
            c = line[i]
            if in_q:
                if c == '"' and i + 1 < n and line[i + 1] == '"':
                    cur += '"'
                    i += 2
                    continue
                if c == '"':
                    in_q = False
                else:
                    cur += c
            else:
                if c == '"':
                    in_q = True
                elif c == ",":
                    cells.append(cur)
                    cur = ""
                else:
                    cur += c
            i += 1
        cells.append(cur)
        rows.append(cells)
    return rows


_NEEDS_QUOTING = re.compile(r'[",\n]')


def csv_escape(v: object) -> str:
    s = "" if v is None else str(v)
    if _NEEDS_QUOTING.search(s):
        return '"' + s.replace('"', '""') + '"'
    return s


def parse_share(value: str) -> float:
    s = (value or "").replace(",", ".").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def emit_cleaned(catalog_rows: list[list[str]]) -> str:
    if not catalog_rows:
        return ""
    out = [",".join(catalog_rows[0])]
    for row in catalog_rows[1:]:
        out.append(",".join(csv_escape(v) for v in row))
    return "\n".join(out)
