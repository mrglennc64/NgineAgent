"""
Source:
  - traproyalties-new1/api/utils/musicbrainz_audit.py (penalty rubric)
  - traproyalties-new1/api/services/forensic_pipeline.py :: _detect_gaps + _build_verdict
  - traproyalties-new1/api/services/forensic_pipeline.py :: _check_statute

The original pulls metadata from MusicBrainz/Discogs/ListenBrainz over HTTP.
This port works only on data already present in the uploaded file — no network calls,
no external dependencies beyond pandas. The scoring rubric (work-rel -35, IPI -10,
IPI+ISNI -20, no-releases -15, short-track -5) is preserved.
"""

from typing import List, Dict
import pandas as pd

from .base_validator import BaseValidator
from ..utils.health_score import get_risk_status, revenue_impact
from ..utils.statute import check_age


PENALTIES = {
    "missing_iswc": 35,        # Mechanical royalties blocked
    "missing_ipi_and_isni": 20,
    "missing_ipi_only": 10,
    "no_release_history": 15,  # If release_date is absent entirely
    "short_recording": 5,      # duration_seconds < 120
}


class MusicValidator(BaseValidator):
    """Music-domain validator — schema rules + royalty-gap detection per row."""

    def validate(self, df: pd.DataFrame) -> List[Dict]:
        issues = super().validate(df)
        issues.extend(self._gap_findings(df))
        issues.extend(self._statute_findings(df))
        return issues

    def _gap_findings(self, df: pd.DataFrame) -> List[Dict]:
        findings: List[Dict] = []

        has_iswc_col = "iswc" in df.columns
        has_ipi_col = "ipi" in df.columns
        has_isni_col = "isni" in df.columns
        has_duration_col = "duration_seconds" in df.columns
        has_release_col = "release_date" in df.columns

        for idx, row in df.iterrows():
            row_score = 100
            row_loss = 0

            if has_iswc_col and self._blank(row.get("iswc")):
                row_score -= PENALTIES["missing_iswc"]
                row_loss += PENALTIES["missing_iswc"]
                findings.append({
                    "row": int(idx),
                    "field": "iswc",
                    "severity": "HIGH",
                    "message": "No ISWC — composition not linked. Mechanical royalties cannot be attributed.",
                    "fix": "Register the composition with a PRO (ASCAP/BMI/SESAC) to obtain an ISWC.",
                })

            ipi_blank = has_ipi_col and self._blank(row.get("ipi"))
            isni_blank = has_isni_col and self._blank(row.get("isni"))

            if ipi_blank and isni_blank:
                row_score -= PENALTIES["missing_ipi_and_isni"]
                row_loss += PENALTIES["missing_ipi_and_isni"]
                findings.append({
                    "row": int(idx),
                    "field": "ipi",
                    "severity": "MEDIUM",
                    "message": "Artist has neither IPI nor ISNI. Performance royalties cannot route.",
                    "fix": "Register with a PRO to receive an IPI number.",
                })
            elif ipi_blank:
                row_score -= PENALTIES["missing_ipi_only"]
                row_loss += PENALTIES["missing_ipi_only"]
                findings.append({
                    "row": int(idx),
                    "field": "ipi",
                    "severity": "MEDIUM",
                    "message": "Missing IPI number. Performance royalties may be delayed.",
                    "fix": "Get an IPI from your PRO.",
                })

            if has_release_col and self._blank(row.get("release_date")):
                row_score -= PENALTIES["no_release_history"]
                row_loss += PENALTIES["no_release_history"]
                findings.append({
                    "row": int(idx),
                    "field": "release_date",
                    "severity": "LOW",
                    "message": "No release_date on record. Streaming platforms may not display the track correctly.",
                    "fix": "Add the original release date.",
                })

            if has_duration_col:
                try:
                    secs = float(row.get("duration_seconds"))
                    if 0 < secs < 120:
                        row_score -= PENALTIES["short_recording"]
                        row_loss += PENALTIES["short_recording"]
                        findings.append({
                            "row": int(idx),
                            "field": "duration_seconds",
                            "severity": "LOW",
                            "message": f"Short recording: {secs:.0f}s. Some platforms have minimum play time requirements.",
                            "fix": "Confirm track meets platform requirements (>120s recommended).",
                        })
                except (ValueError, TypeError):
                    pass

            if row_loss > 0:
                findings.append({
                    "row": int(idx),
                    "field": "__health__",
                    "severity": "INFO",
                    "message": f"Row health: {row_score}/100 ({get_risk_status(row_score)})",
                    "health_score": max(0, row_score),
                    "estimated_loss_pct": row_loss,
                    "revenue_impact": revenue_impact(row_loss),
                })

        return findings

    def _statute_findings(self, df: pd.DataFrame) -> List[Dict]:
        if "release_date" not in df.columns:
            return []
        out: List[Dict] = []
        for idx, value in df["release_date"].items():
            if self._blank(value):
                continue
            check = check_age(str(value))
            if check is None:
                continue
            out.append({
                "row": int(idx),
                "field": "release_date",
                "severity": "HIGH" if check["level"] == "urgent" else "MEDIUM",
                "message": (
                    f"{check['label']} (released {check['age_years']} years ago). "
                    "17 U.S.C. § 507(b) — 3-year statute of limitations on royalty claims."
                ),
                "statute": check,
            })
        return out

    @staticmethod
    def _blank(value) -> bool:
        if value is None:
            return True
        try:
            if pd.isna(value):
                return True
        except (TypeError, ValueError):
            pass
        return str(value).strip() == ""
