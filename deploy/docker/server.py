"""
FastAPI server wrapping the passport OCR pipeline.

Used by the document-ocr npm package to run OCR locally.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import secrets
import uuid

from fastapi import FastAPI, File, Header, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from core.kyc_ocr import KycOCRConfigError
from core.ocr_engine import OCRModelInitError
from core.pipeline import scan
from core.preprocessor import ImageQualityError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
logger = logging.getLogger("document-ocr")
API_TOKEN = os.getenv("DOCUMENT_OCR_API_TOKEN") or None

_ocr_semaphore = asyncio.Semaphore(1)
_models_ready = False
_model_init_error: str | None = None

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _models_ready, _model_init_error
    _models_ready = False
    _model_init_error = None
    logger.info("Loading OCR models...")
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _warm_up_ocr)
    except (OCRModelInitError, KycOCRConfigError) as exc:
        # Stay up so /ready and /scan can report a clear error instead of the
        # process crash-looping. Liveness (/health) remains green.
        _model_init_error = str(exc)
        logger.error("OCR model initialisation failed: %s", exc)
    else:
        _models_ready = True
        logger.info("OCR models loaded.")
    yield


app = FastAPI(title="Document OCR", version="3.0.0", lifespan=_lifespan)


def _warm_up_ocr():
    from core.kyc_ocr import configured_kyc_languages
    from core.ocr_engine import _get_ocr

    for language in dict.fromkeys(("en", *configured_kyc_languages())):
        _get_ocr(language)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if _model_init_error is not None:
        return JSONResponse(
            status_code=503,
            content={"status": "model_init_failed", "error": _model_init_error},
        )
    if not _models_ready:
        return JSONResponse(status_code=503, content={"status": "loading"})
    return {"status": "ready"}


@app.post("/scan")
async def scan_passport(
    image: UploadFile = File(...),
    authorization: str | None = Header(default=None),
):
    request_id = str(uuid.uuid4())[:8]

    if API_TOKEN is not None:
        expected = f"Bearer {API_TOKEN}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            raise HTTPException(
                status_code=401,
                detail="UNAUTHORIZED",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # Validate content type
    content_type = image.content_type or ""
    if not content_type.startswith("image/") and content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="INVALID_CONTENT_TYPE")

    # Read and check size
    data = await image.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="FILE_TOO_LARGE")

    if len(data) == 0:
        raise HTTPException(status_code=400, detail="EMPTY_FILE")

    # Run pipeline
    try:
        async with _ocr_semaphore:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, scan, data),
                timeout=60.0,
            )
    except asyncio.TimeoutError:
        logger.warning(f"[{request_id}] scan_timeout")
        return JSONResponse(status_code=504, content={"error": "SCAN_TIMEOUT"})
    except OCRModelInitError as e:
        logger.error(f"[{request_id}] model_init_failed={e}")
        return JSONResponse(status_code=503, content={"error": "MODEL_INIT_FAILED"})
    except KycOCRConfigError as e:
        logger.error(f"[{request_id}] invalid_kyc_ocr_config={e}")
        return JSONResponse(status_code=503, content={"error": "INVALID_KYC_OCR_CONFIG"})
    except ImageQualityError as e:
        logger.info(f"[{request_id}] quality_error={e}")
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception:
        logger.exception(f"[{request_id}] internal_error")
        return JSONResponse(
            status_code=500,
            content={"error": "INTERNAL_ERROR"},
        )

    # Log only non-PII fields
    logger.info(
        f"[{request_id}] status={result.status} "
        f"page_type={result.page_type} "
        f"confidence={result.confidence} "
        f"processing_ms={result.processing_ms} "
        f"errors={result.errors}"
    )

    if result.status == "failure":
        return JSONResponse(status_code=422, content=result.to_dict())

    return result.to_dict()
