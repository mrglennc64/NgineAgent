"""
Source: traproyalties-new1/api/services/contract_parser.py :: apply_to_isrcs (pattern)

The original applies extracted splits across all ISRCs for an artist via a DB call.
This port keeps the pattern (one set of corrections applied to many identifier rows)
but adds music-specific guard rails before persisting:
  - Split-percentage fields (writer_share, publisher_share, master_share) must sum to 100.
  - Worksheet rows targeting split fields are validated together per row before write.
"""

from typing import List
import pandas as pd

from .base_corrector import BaseCorrector


SPLIT_FIELDS = {"writer_share", "publisher_share", "master_share"}


class MusicCorrector(BaseCorrector):

    def apply_corrections(self, df: pd.DataFrame, worksheet: pd.DataFrame) -> pd.DataFrame:
        corrected = super().apply_corrections(df, worksheet)
        self._validate_split_sums(corrected)
        return corrected

    @staticmethod
    def _validate_split_sums(df: pd.DataFrame) -> None:
        present = [f for f in SPLIT_FIELDS if f in df.columns]
        if not present:
            return
        for idx, row in df.iterrows():
            try:
                total = sum(float(row[f]) for f in present if not pd.isna(row[f]))
            except (TypeError, ValueError):
                continue
            if total and abs(total - 100.0) > 0.5:
                raise ValueError(
                    f"Row {idx}: split fields {present} sum to {total:.2f}, expected 100. "
                    f"Adjust the worksheet before applying."
                )
