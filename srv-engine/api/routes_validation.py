import io

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
import pandas as pd

from services.validate import validate_file
from services.generate_worksheet import generate_worksheet


router = APIRouter()


def _read_upload(file: UploadFile, content: bytes) -> pd.DataFrame:
    name = (file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            return pd.read_excel(io.BytesIO(content))
        return pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse uploaded file: {e}")


@router.post("/validate")
async def validate_endpoint(
    request: Request,
    file: UploadFile = File(...),
    domain: str = Form("music"),
):
    request.state.domain = domain
    content = await file.read()
    df = _read_upload(file, content)
    issues = validate_file(df, domain=domain)
    return {
        "domain": domain,
        "rows": int(len(df)),
        "issue_count": len(issues),
        "issues": issues,
    }


@router.post("/worksheet")
async def worksheet_endpoint(
    request: Request,
    file: UploadFile = File(...),
    domain: str = Form("music"),
):
    request.state.domain = domain
    content = await file.read()
    df = _read_upload(file, content)
    issues = validate_file(df, domain=domain)
    ws = generate_worksheet(df, issues)
    return {
        "domain": domain,
        "issue_count": len(issues),
        "worksheet": ws.fillna("").to_dict(orient="records"),
    }
