import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse

from core.utils.stats import stats

from .routes_validation import router as validation_router
from .routes_correction import router as correction_router
from .routes_export import router as export_router


app = FastAPI(title="Generic Validation/Correction Engine", version="0.1.0")


@app.middleware("http")
async def record_stats(request: Request, call_next):
    if request.url.path in ("/dashboard", "/stats", "/health", "/openapi.json", "/docs", "/redoc", "/"):
        return await call_next(request)
    start = time.perf_counter()
    domain = None
    try:
        ct = (request.headers.get("content-type") or "").lower()
        if "multipart/form-data" in ct:
            pass
        else:
            domain = request.query_params.get("domain")
    except Exception:
        pass

    try:
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        d = getattr(request.state, "domain", None) or domain
        stats.record(request.url.path, request.method, response.status_code, ms, d)
        if response.status_code >= 500:
            stats.record_error(request.url.path, f"HTTP {response.status_code}")
        return response
    except Exception as e:
        ms = (time.perf_counter() - start) * 1000
        stats.record(request.url.path, request.method, 500, ms, None)
        stats.record_error(request.url.path, f"{type(e).__name__}: {e}")
        raise


app.include_router(validation_router, prefix="/validation", tags=["validation"])
app.include_router(correction_router, prefix="/correction", tags=["correction"])
app.include_router(export_router, prefix="/export", tags=["export"])


_STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(_STATIC_DIR / "landing.html", media_type="text/html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats", tags=["dashboard"])
def get_stats():
    return stats.snapshot()


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(_STATIC_DIR / "dashboard.html", media_type="text/html")
