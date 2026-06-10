"""
Source: traproyalties-new1/api/services/forensic_pipeline.py :: _check_statute

US copyright statute of limitations (17 U.S.C. § 507(b), 3 years) is music-specific,
but the underlying date-aging check is generic. Configurable thresholds let other
domains (e.g. invoices past-due) reuse it.
"""

from datetime import datetime, timezone
from typing import Optional, Dict


def check_age(
    date_str: Optional[str],
    urgent_years: float = 3.0,
    warning_years: float = 2.5,
    urgent_label: str = "STATUTE — FILE IMMEDIATELY",
    warning_label_fmt: str = "STATUTE WARNING — ~{months} months remaining",
) -> Optional[Dict]:
    if not date_str:
        return None
    try:
        parts = str(date_str).split("-")
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        anchor = datetime(year, month, day, tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        age_years = (now - anchor).days / 365.25

        if age_years >= urgent_years:
            return {
                "level": "urgent",
                "label": urgent_label,
                "color": "red",
                "age_years": round(age_years, 1),
                "date": date_str,
            }
        if age_years >= warning_years:
            remaining_months = round((urgent_years - age_years) * 12)
            return {
                "level": "warning",
                "label": warning_label_fmt.format(months=remaining_months),
                "color": "yellow",
                "age_years": round(age_years, 1),
                "remaining_months": remaining_months,
                "date": date_str,
            }
        return None
    except (ValueError, IndexError, TypeError):
        return None
