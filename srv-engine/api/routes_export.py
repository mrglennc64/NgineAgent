import io

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response
import pandas as pd

from services.export_file import export_corrected, media_type_for, filename_for


router = APIRouter()


@router.post("/file")
async def export_endpoint(
    corrected_file: UploadFile = File(...),
    fmt: str = Form("csv"),
):
    content = await corrected_file.read()
    name = (corrected_file.filename or "").lower()
    try:
        if name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(content))
        else:
            df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse {corrected_file.filename}: {e}")

    data = export_corrected(df, fmt=fmt)
    return Response(
        content=data,
        media_type=media_type_for(fmt),
        headers={"Content-Disposition": f"attachment; filename={filename_for(fmt)}"},
    )
