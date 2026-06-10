from typing import List, Dict
import pandas as pd


class BaseValidator:
    def __init__(self, schema: dict, rules: dict):
        self.schema = schema
        self.rules = rules

    def validate(self, df: pd.DataFrame) -> List[Dict]:
        issues: List[Dict] = []
        required_fields = self.schema.get("required", [])
        for field in required_fields:
            if field not in df.columns:
                issues.append({
                    "row": None,
                    "field": field,
                    "severity": "HIGH",
                    "message": "Missing required column",
                })
                continue
            missing_mask = df[field].isna() | (df[field].astype(str).str.strip() == "")
            for idx in df[missing_mask].index:
                issues.append({
                    "row": int(idx),
                    "field": field,
                    "severity": "HIGH",
                    "message": "Missing value",
                })

        for field, spec in self.schema.get("fields", {}).items():
            if field not in df.columns:
                continue
            pattern = spec.get("pattern")
            if pattern:
                mask = df[field].notna() & ~df[field].astype(str).str.replace(r"\.0$", "", regex=True).str.match(pattern)
                for idx in df[mask].index:
                    issues.append({
                        "row": int(idx),
                        "field": field,
                        "severity": spec.get("severity", "MEDIUM"),
                        "message": spec.get("pattern_message", f"Invalid format for {field}"),
                    })

        return issues
