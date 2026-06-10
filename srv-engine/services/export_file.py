import pandas as pd

from core.exporters.csv_exporter import export_csv
from core.exporters.xlsx_exporter import export_xlsx
from core.exporters.pdf_exporter import export_pdf


def export_corrected(df: pd.DataFrame, fmt: str = "csv", domain: str | None = None) -> bytes:
    fmt = (fmt or "csv").lower()
    if fmt in ("xlsx", "excel"):
        return export_xlsx(df)
    if fmt == "pdf":
        return export_pdf(df, domain=domain)
    return export_csv(df)


def media_type_for(fmt: str) -> str:
    fmt = (fmt or "").lower()
    if fmt in ("xlsx", "excel"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt == "pdf":
        return "application/pdf"
    return "text/csv"


def filename_for(fmt: str, stem: str = "corrected") -> str:
    fmt = (fmt or "").lower()
    if fmt in ("xlsx", "excel"):
        return f"{stem}.xlsx"
    if fmt == "pdf":
        return f"{stem}.pdf"
    return f"{stem}.csv"
