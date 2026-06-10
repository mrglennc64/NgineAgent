from typing import Literal
import pandas as pd

from core.utils.schema_loader import load_schema
from core.utils.rule_loader import load_rules
from core.validators.base_validator import BaseValidator
from core.validators.music_validator import MusicValidator


Domain = Literal["music", "healthcare", "invoice", "payroll", "base"]


def get_validator(domain: str, schema: dict, rules: dict) -> BaseValidator:
    if domain == "music":
        return MusicValidator(schema, rules)
    return BaseValidator(schema, rules)


def validate_file(df: pd.DataFrame, domain: str = "music"):
    schema = load_schema(domain)
    rules = load_rules(domain)
    validator = get_validator(domain, schema, rules)
    return validator.validate(df)
