from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .constants import (
    DECLARATION_ROLES,
    FOREIGN_SOCIETIES,
    VALID_ROLES,
)
from .csv_io import parse_csv, parse_share

Severity = Literal["blocking", "resolvable"]
Field = Literal[
    "iswc",
    "isrc",
    "split_total",
    "writer_ipi",
    "society",
    "foreign_writer",
    "role",
    "writer_name",
]


@dataclass
class Issue:
    id: str
    work: str
    field: Field
    current: str
    suggested: str
    severity: Severity


@dataclass
class Contributor:
    name: str
    role: str
    share: float
    ipi: str
    society: str
    iswc: str
    isrc: str


@dataclass
class Work:
    title: str
    contribs: list[Contributor]


@dataclass
class ScanResult:
    titles: list[str]
    works: dict[str, Work]
    issues: list[Issue]
    blocking: int
    resolvable: int
    score: int
    total_contribs: int


_NAME_VARIANT_RE = re.compile(r"^[A-ZÅÄÖ]\.?\s+[A-Za-zÅÄÖåäö]+$")
_WS_RE = re.compile(r"\s+")


def _build_works(catalog_text: str) -> tuple[list[str], dict[str, Work]]:
    rows = parse_csv(catalog_text)
    if len(rows) < 2:
        raise ValueError("CSV must have a header + at least 1 row.")

    header = [h.strip().lower() for h in rows[0]]

    def col(name: str) -> int:
        return header.index(name) if name in header else -1

    ti = col("title")
    ni = col("name")
    if ti < 0 or ni < 0:
        raise ValueError("Catalog must have title + name columns.")

    iswc_i = col("iswc")
    isrc_i = col("isrc")
    ri = col("role")
    si = col("share_percent")
    ii = col("ipi")
    soi = col("society")

    def cell(row: list[str], idx: int) -> str:
        if idx < 0 or idx >= len(row):
            return ""
        return (row[idx] or "").strip()

    works: dict[str, Work] = {}
    for row in rows[1:]:
        title = (row[ti] if ti < len(row) else "").strip() if ti >= 0 else ""
        if not title:
            continue
        if title not in works:
            works[title] = Work(title=title, contribs=[])
        works[title].contribs.append(
            Contributor(
                name=cell(row, ni),
                role=cell(row, ri),
                share=parse_share(row[si] if 0 <= si < len(row) else ""),
                ipi=cell(row, ii),
                society=cell(row, soi),
                iswc=cell(row, iswc_i),
                isrc=cell(row, isrc_i),
            )
        )

    titles = list(works.keys())
    return titles, works


def detect_issues(catalog_text: str) -> ScanResult:
    titles, works = _build_works(catalog_text)

    issues: list[Issue] = []
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"HR-{counter:03d}"

    all_names = list(
        dict.fromkeys(
            c.name for t in titles for c in works[t].contribs if c.name
        )
    )

    for t in titles:
        w = works[t]
        c0 = w.contribs[0] if w.contribs else None

        if c0 is not None and not c0.iswc:
            issues.append(
                Issue(
                    id=next_id(),
                    work=t,
                    field="iswc",
                    current="missing",
                    suggested="external lookup match",
                    severity="resolvable",
                )
            )

        total = sum(c.share for c in w.contribs)
        if abs(total - 100) > 0.5:
            issues.append(
                Issue(
                    id=next_id(),
                    work=t,
                    field="split_total",
                    current=f"{total:.2f}%",
                    suggested="normalize to 100%",
                    severity="blocking",
                )
            )

    for t in titles:
        contribs = works[t].contribs
        for c in contribs:
            if c.name and not c.ipi:
                issues.append(
                    Issue(
                        id=next_id(),
                        work=t,
                        field="writer_ipi",
                        current=f"{c.name} has no IPI",
                        suggested="publisher to provide",
                        severity="blocking",
                    )
                )

            if c.name and not c.society:
                issues.append(
                    Issue(
                        id=next_id(),
                        work=t,
                        field="society",
                        current=f"{c.name} — missing society",
                        suggested="publisher to confirm",
                        severity="resolvable",
                    )
                )

            if c.society and c.society.upper() in FOREIGN_SOCIETIES:
                has_decl = any(
                    (x.role or "").upper() in DECLARATION_ROLES for x in contribs
                )
                if not has_decl:
                    issues.append(
                        Issue(
                            id=next_id(),
                            work=t,
                            field="foreign_writer",
                            current=f"{c.name} ({c.society}) — no E/SE/AM declaration",
                            suggested="add E declaration",
                            severity="blocking",
                        )
                    )

            if c.role and c.role.upper() not in VALID_ROLES:
                issues.append(
                    Issue(
                        id=next_id(),
                        work=t,
                        field="role",
                        current=f"{c.role} ({c.name})",
                        suggested="change to CA (CWR-valid)",
                        severity="blocking",
                    )
                )

            if c.name and _NAME_VARIANT_RE.match(c.name.strip()):
                stripped = c.name.strip()
                initial = stripped[0].lower()
                surname = _WS_RE.split(stripped)[-1].lower()
                for other in all_names:
                    if other == c.name:
                        continue
                    parts = _WS_RE.split(other.lower())
                    if (
                        len(parts) >= 2
                        and parts[0][:1] == initial
                        and parts[-1] == surname
                    ):
                        issues.append(
                            Issue(
                                id=next_id(),
                                work=t,
                                field="writer_name",
                                current=c.name,
                                suggested=f"{other} (canonical)",
                                severity="resolvable",
                            )
                        )
                        break

    blocking = sum(1 for i in issues if i.severity == "blocking")
    resolvable = sum(1 for i in issues if i.severity == "resolvable")
    score = max(0, min(100, 100 - 6 * blocking - 1 * resolvable))
    total_contribs = sum(len(works[t].contribs) for t in titles)

    return ScanResult(
        titles=titles,
        works=works,
        issues=issues,
        blocking=blocking,
        resolvable=resolvable,
        score=score,
        total_contribs=total_contribs,
    )
