from __future__ import annotations

from .csv_io import csv_escape
from .detect import ScanResult


def build_worksheet_csv(scan: ScanResult) -> str:
    """CSV worksheet matching internal-tools-spec §2.2."""
    header = "issue_id,work,field,current_value,suggested,decision,publisher_value,note"
    lines = [header]
    for i in scan.issues:
        lines.append(
            ",".join(
                csv_escape(v) for v in [i.id, i.work, i.field, i.current, i.suggested, "", "", ""]
            )
        )
    return "\n".join(lines)
