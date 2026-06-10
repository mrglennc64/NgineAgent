from typing import List, Dict
import pandas as pd

from core.worksheet.generator import generate_worksheet as _gen


def generate_worksheet(df: pd.DataFrame, issues: List[Dict]) -> pd.DataFrame:
    return _gen(df, issues)
