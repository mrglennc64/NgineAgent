import pandas as pd

from core.correctors.base_corrector import BaseCorrector
from core.correctors.music_corrector import MusicCorrector


def get_corrector(domain: str) -> BaseCorrector:
    if domain == "music":
        return MusicCorrector()
    return BaseCorrector()


def apply_corrections(df: pd.DataFrame, worksheet: pd.DataFrame, domain: str = "music") -> pd.DataFrame:
    corrector = get_corrector(domain)
    return corrector.apply_corrections(df, worksheet)
