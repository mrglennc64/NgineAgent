"""
Source: traproyalties-new1/api/utils/musicbrainz_audit.py
        get_risk_status / get_risk_color / get_risk_message and the
        revenue-impact split (40/30/20/10) for streaming/mechanical/performance/sync.

De-coupled from MusicBrainz / ListenBrainz / requests. Pure functions over a numeric score.
"""

from typing import Dict


def get_risk_status(score: int) -> str:
    if score >= 90:
        return "SECURE"
    if score >= 70:
        return "AT_RISK"
    return "CRITICAL"


def get_risk_color(score: int) -> str:
    if score >= 90:
        return "green"
    if score >= 70:
        return "yellow"
    return "red"


def get_risk_message(score: int) -> str:
    if score >= 90:
        return "Metadata is complete. All royalty paths should be open."
    if score >= 70:
        return "Some identifiers missing. International royalties may be delayed."
    return "Critical issues found. Revenue leakage likely."


def revenue_impact(estimated_loss_pct: float, weights: Dict[str, float] = None) -> Dict[str, float]:
    if weights is None:
        weights = {"streaming": 0.4, "mechanical": 0.3, "performance": 0.2, "sync": 0.1}
    out = {k: round(estimated_loss_pct * w, 1) for k, w in weights.items()}
    out["total"] = round(estimated_loss_pct, 1)
    return out


def score_to_health(score: int, estimated_loss_pct: float = None, weights: Dict[str, float] = None) -> Dict:
    if estimated_loss_pct is None:
        estimated_loss_pct = max(0, 100 - score)
    return {
        "score": max(0, min(100, score)),
        "status": get_risk_status(score),
        "color": get_risk_color(score),
        "message": get_risk_message(score),
        "estimated_loss_pct": estimated_loss_pct,
        "revenue_impact": revenue_impact(estimated_loss_pct, weights),
    }
