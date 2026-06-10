import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]


def load_rules(domain: str) -> dict:
    rules_path = BASE_DIR / "rules" / f"{domain}_rules.json"
    if not rules_path.exists():
        return {}
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)
