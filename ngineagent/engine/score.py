from __future__ import annotations

from typing import Literal

Tone = Literal["good", "warn", "bad"]


def health_score(blocking: int, resolvable: int) -> int:
    return max(0, min(100, 100 - 6 * blocking - 1 * resolvable))


def classify_tone(score: int) -> Tone:
    if score >= 80:
        return "good"
    if score >= 50:
        return "warn"
    return "bad"
