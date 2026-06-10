import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from services.export_file import export_corrected
from core.exporters.ddex_exporter import DDEXGenerator, validate_ern, validate_release_data


def test_export_csv():
    df = pd.DataFrame([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    data = export_corrected(df, fmt="csv")
    assert b"a,b" in data
    assert b"1,x" in data


def test_export_xlsx_starts_with_zip_magic():
    df = pd.DataFrame([{"a": 1}])
    data = export_corrected(df, fmt="xlsx")
    assert data[:2] == b"PK"  # XLSX is a ZIP archive


def test_ddex_generate_and_validate_round_trip():
    data = {
        "id": "REL001",
        "title": "Test Single",
        "artist": "Test Artist",
        "artist_id": "001",
        "label_name": "Test Label",
        "label_id": "002",
        "release_date": "2025-06-01",
        "tracks": [
            {"title": "Test Single", "isrc": "USRC12345678", "duration": "PT3M00S"},
        ],
    }
    ok, errs = validate_release_data(data)
    assert ok, errs

    gen = DDEXGenerator(version="4.3")
    result = gen.generate(data)
    assert "<NewReleaseMessage" in result["xml"]
    assert result["hash"]

    is_valid, errors = validate_ern(result["xml"])
    assert is_valid, errors


def test_ddex_missing_required_caught_by_release_validator():
    data = {"artist": "X"}  # missing title, release_date, label_name
    ok, errs = validate_release_data(data)
    assert not ok
    assert any("title" in e for e in errs)
