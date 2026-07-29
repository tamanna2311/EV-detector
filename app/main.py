"""FastAPI application factory and production entry point."""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.routes import router
from app.config import ROOT, settings
from app.csv_io import CsvValidationError
from app.middleware import (
    ContentLengthMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from app.ml.features import SignalValidationError
from app.ml.predictor import SpectralPredictor


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        )


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=settings.log_level, handlers=[handler], force=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.predictor = SpectralPredictor(settings.model_path)
    logging.getLogger(__name__).info(
        "model_loaded version=%s", app.state.predictor.version
    )
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="EV Detector API",
        summary="Detect EV vs non-EV from smartphone accelerometer recordings.",
        description=(
            "A research-grounded spectral classifier that looks for stable "
            "combustion-engine vibrations during stopped or near-stopped periods. "
            "The confidence field is model confidence, not a real-world accuracy "
            "guarantee."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        contact={
            "name": "EV Detector",
            "url": "https://github.com/tamanna2311/EV-detector",
        },
        license_info={"name": "MIT", "identifier": "MIT"},
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(ContentLengthMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts)
    )

    application.include_router(router)

    @application.get("/", include_in_schema=False)
    async def landing_page() -> FileResponse:
        return FileResponse(Path(ROOT / "app" / "static" / "index.html"))

    @application.middleware("http")
    async def access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        logging.getLogger("ev_detector.access").info(
            "method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.perf_counter() - started) * 1000,
            getattr(request.state, "request_id", ""),
        )
        return response

    @application.exception_handler(SignalValidationError)
    @application.exception_handler(CsvValidationError)
    async def signal_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_SIGNAL",
                    "message": str(exc),
                    "request_id": getattr(request.state, "request_id", ""),
                }
            },
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first_error = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first_error.get("loc", []))
        message = first_error.get("msg", "Request validation failed.")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "INVALID_REQUEST",
                    "message": f"{location}: {message}" if location else message,
                    "request_id": getattr(request.state, "request_id", ""),
                }
            },
        )

    return application


app = create_app()
