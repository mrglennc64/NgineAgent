"""
Source: traproyalties-new1/api/services/cleanup_recommendations_with_shazam.py
        Priority-scoring loop (base score + traction multiplier + spike boost + velocity boost).

De-coupled from the Shazam API + DB. The same priority math is applied generically:
the *issue* carries the base weight (via severity), and optional per-row traction/spike
hints (from extra columns like 'traction_score', 'has_spike', 'velocity_score') multiply
the priority. If those columns aren't present, only severity determines priority.
"""

from typing import List, Dict, Optional
import pandas as pd


SEVERITY_BASE = {"HIGH": 25, "MEDIUM": 15, "LOW": 5, "INFO": 0}


def _priority_for(row_idx: Optional[int], severity: str, df: pd.DataFrame) -> float:
    base = SEVERITY_BASE.get((severity or "LOW").upper(), 5)
    if row_idx is None or row_idx not in df.index:
        return float(base)

    priority = float(base)
    row = df.loc[row_idx]

    # Traction multiplier (0-100 scale)
    traction = _safe_num(row.get("traction_score")) if "traction_score" in df.columns else 0
    if traction:
        priority *= 1 + (traction / 100.0)

    # Shazam spike boost (3x)
    if "has_spike" in df.columns:
        spike_val = row.get("has_spike")
        if str(spike_val).strip().lower() in ("true", "1", "yes"):
            priority *= 3.0

    # Shazam index tiers (2x / 1.5x)
    elif "shazam_index" in df.columns:
        sx = _safe_num(row.get("shazam_index"))
        if sx > 50:
            priority *= 2.0
        elif sx > 20:
            priority *= 1.5

    # Velocity multiplier (0-50 scale)
    velocity = _safe_num(row.get("velocity_score")) if "velocity_score" in df.columns else 0
    if velocity:
        priority *= 1 + (velocity / 50.0)

    return priority


def _safe_num(value) -> float:
    try:
        if value is None:
            return 0.0
        if pd.isna(value):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_message(severity: str, base_message: str, has_spike: bool) -> str:
    if has_spike:
        return f"URGENT - SHAZAM SPIKE: {base_message}"
    if severity == "HIGH":
        return f"URGENT: {base_message}"
    if severity == "MEDIUM":
        return f"Needed: {base_message}"
    return base_message


def generate_worksheet(df: pd.DataFrame, issues: List[Dict]) -> pd.DataFrame:
    rows: List[Dict] = []
    for issue in issues:
        row_idx = issue.get("row")
        field = issue.get("field")
        severity = issue.get("severity", "LOW")

        original = None
        if row_idx is not None and field in df.columns:
            try:
                value = df.loc[row_idx, field]
                if pd.isna(value):
                    original = None
                else:
                    original = value.item() if hasattr(value, "item") else value
            except (KeyError, IndexError):
                original = None

        has_spike = False
        if row_idx is not None and "has_spike" in df.columns and row_idx in df.index:
            has_spike = str(df.loc[row_idx, "has_spike"]).strip().lower() in ("true", "1", "yes")

        priority = _priority_for(row_idx, severity, df)
        message = _format_message(severity, issue.get("message", ""), has_spike)

        rows.append({
            "row": row_idx,
            "field": field,
            "original": original,
            "correction": "",
            "severity": severity,
            "priority": round(priority, 1),
            "message": message,
            "fix": issue.get("fix", ""),
            "notes": "",
        })

    ws = pd.DataFrame(rows)
    if not ws.empty:
        ws = ws.sort_values("priority", ascending=False).reset_index(drop=True)
    return ws
