import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import pytest

from services.apply_corrections import apply_corrections


def test_apply_simple_correction():
    df = pd.DataFrame([
        {"title": "X", "artist": "Y", "isrc": ""},
        {"title": "Z", "artist": "W", "isrc": "USRC99999999"},
    ])
    ws = pd.DataFrame([
        {"row": 0, "field": "isrc", "correction": "USRC11111111"},
        {"row": 1, "field": "isrc", "correction": ""},
    ])
    corrected = apply_corrections(df, ws, domain="music")
    assert corrected.loc[0, "isrc"] == "USRC11111111"
    assert corrected.loc[1, "isrc"] == "USRC99999999"  # blank correction ignored


def test_split_sum_validation():
    df = pd.DataFrame([{
        "title": "X", "artist": "Y", "isrc": "USRC11111111",
        "writer_share": 50, "publisher_share": 50,
    }])
    ws = pd.DataFrame([
        {"row": 0, "field": "writer_share", "correction": 60},
    ])
    with pytest.raises(ValueError, match="sum to"):
        apply_corrections(df, ws, domain="music")


def test_base_corrector_ignores_split_rules():
    df = pd.DataFrame([{"x": "a"}])
    ws = pd.DataFrame([{"row": 0, "field": "x", "correction": "b"}])
    corrected = apply_corrections(df, ws, domain="base")
    assert corrected.loc[0, "x"] == "b"
