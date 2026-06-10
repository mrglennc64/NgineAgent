import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def load_schema(schema_name: str) -> dict:
    schema_path = BASE_DIR / "schemas" / f"{schema_name}_schema.json"
    if not schema_path.exists():
        schema_path = BASE_DIR / "schemas" / "base_schema.json"
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)
