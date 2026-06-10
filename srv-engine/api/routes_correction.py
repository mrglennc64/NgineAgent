import io

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
import numpy as np
import pandas as pd

from services.apply_corrections import apply_corrections


router = APIRouter()


def _read(file: UploadFile, content: bytes) -> pd.DataFrame:
    name = (file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(content))
        return pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse {file.filename}: {e}")


def _json_safe(df: pd.DataFrame) -> list:
    """Replace NaN/Inf with None so FastAPI's strict JSON encoder accepts the output."""
    return df.replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict(orient="records")


@router.post("/apply")
async def apply_corrections_endpoint(
    request: Request,
    original_file: UploadFile = File(...),
    worksheet_file: UploadFile = File(...),
    domain: str = Form("music"),
):
    request.state.domain = domain
    orig_content = await original_file.read()
    ws_content = await worksheet_file.read()

    df = _read(original_file, orig_content)
    ws = _read(worksheet_file, ws_content)

    try:
        corrected = apply_corrections(df, ws, domain=domain)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "domain": domain,
        "rows": int(len(corrected)),
        "preview": _json_safe(corrected.head(20)),
    }
