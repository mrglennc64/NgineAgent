"""
Render a corrected DataFrame to a single-table PDF.

Uses reportlab (pure-Python, no system dependencies) so it deploys on the VPS
without extra OS packages. The output is a landscape table with a repeating
header row — the same data you'd get from csv/xlsx, just print-ready.
"""

import io

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


# Cells longer than this are truncated so wide catalogs stay readable on one page width.
_MAX_CELL_CHARS = 60


def _stringify(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    if len(text) > _MAX_CELL_CHARS:
        return text[: _MAX_CELL_CHARS - 1] + "…"
    return text


def export_pdf(df: pd.DataFrame, title: str = "Corrected Data") -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=0.4 * inch,
        rightMargin=0.4 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=title,
    )

    styles = getSampleStyleSheet()
    elements = [
        Paragraph(title, styles["Title"]),
        Paragraph(f"{len(df)} rows × {len(df.columns)} columns", styles["Normal"]),
        Spacer(1, 0.2 * inch),
    ]

    header = [_stringify(c) for c in df.columns]
    rows = [[_stringify(v) for v in row] for row in df.itertuples(index=False, name=None)]
    data = [header] + rows if rows else [header, ["(no rows)"] + [""] * (len(header) - 1)]

    # Shrink the font as the column count grows so the table fits the page width.
    n_cols = max(len(header), 1)
    font_size = 8 if n_cols <= 8 else 7 if n_cols <= 14 else 6

    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(table)

    doc.build(elements)
    return buf.getvalue()
