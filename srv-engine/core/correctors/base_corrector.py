import pandas as pd


class BaseCorrector:
    def apply_corrections(self, df: pd.DataFrame, worksheet: pd.DataFrame) -> pd.DataFrame:
        corrected = df.copy()
        for _, row in worksheet.iterrows():
            row_idx = row.get("row")
            field = row.get("field")
            correction = row.get("correction")
            if pd.isna(row_idx) or field not in corrected.columns:
                continue
            if correction is None or pd.isna(correction) or str(correction).strip() == "":
                continue
            corrected.loc[int(row_idx), field] = correction
        return corrected
