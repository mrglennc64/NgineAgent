import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from services.validate import validate_file


def test_music_required_field_missing():
    df = pd.DataFrame([
        {"title": "Hello", "artist": "Adele", "isrc": ""},
        {"title": "",      "artist": "Drake", "isrc": "USRC12345678"},
    ])
    issues = validate_file(df, domain="music")
    fields = {(i["row"], i["field"]) for i in issues if i.get("severity") == "HIGH"}
    assert (0, "isrc") in fields
    assert (1, "title") in fields


def test_music_isrc_pattern():
    df = pd.DataFrame([{"title": "X", "artist": "Y", "isrc": "not-an-isrc"}])
    issues = validate_file(df, domain="music")
    pattern_issues = [i for i in issues if i["field"] == "isrc" and "ISRC must" in i["message"]]
    assert pattern_issues, f"Expected ISRC pattern violation, got: {issues}"


def test_music_gap_analysis_missing_iswc_penalty():
    df = pd.DataFrame([{
        "title": "X", "artist": "Y", "isrc": "USRC12345678",
        "iswc": "", "ipi": "123456789",
    }])
    issues = validate_file(df, domain="music")
    iswc_issues = [i for i in issues if i["field"] == "iswc"]
    health = [i for i in issues if i["field"] == "__health__"]
    assert iswc_issues, "Expected ISWC gap finding"
    assert health, "Expected health row"
    assert health[0]["estimated_loss_pct"] >= 35


def test_base_domain_no_required():
    df = pd.DataFrame([{"anything": 1}, {"anything": 2}])
    issues = validate_file(df, domain="base")
    assert issues == []


def test_healthcare_required_fields():
    df = pd.DataFrame([
        {"patient_id": "P1", "encounter_date": "2025-01-01", "provider_npi": "1234567890"},
        {"patient_id": "P2", "encounter_date": "",            "provider_npi": "bad"},
    ])
    issues = validate_file(df, domain="healthcare")
    fields = {(i["row"], i["field"]) for i in issues}
    assert (1, "encounter_date") in fields
    npi_pattern = [i for i in issues if i["field"] == "provider_npi" and i["row"] == 1]
    assert npi_pattern, "Expected NPI pattern violation on row 1"
