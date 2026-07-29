"""Version 1 API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from app import __version__
from app.config import settings
from app.csv_io import parse_accelerometer_csv
from app.schemas import (
    ErrorResponse,
    HealthResponse,
    PredictionRequest,
    PredictionResponse,
)
from app.service import predict_request

router = APIRouter(prefix="/api/v1")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="health_check",
    summary="Liveness and model readiness",
    tags=["System"],
)
async def health(request: Request) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="ev-detector",
        version=__version__,
        model_version=request.app.state.predictor.version,
    )


@router.get(
    "/meta",
    operation_id="service_metadata",
    summary="Model contract and collection guidance",
    tags=["System"],
)
async def metadata(request: Request) -> dict:
    predictor = request.app.state.predictor
    return {
        "service": "EV Detector",
        "version": __version__,
        "model": {
            "version": predictor.version,
            "positive_class": "NON_EV",
            "method": (
                "Orientation-independent magnitude, 2.56-second FFT windows, "
                "19 Hz high-pass features, and regularized logistic regression."
            ),
            "decision_labels": ["EV", "NON_EV", "INCONCLUSIVE"],
        },
        "collection": {
            "units": "m/s²",
            "minimum_sample_rate_hz": 50,
            "recommended_sample_rate_hz": 100,
            "recommended_duration_seconds": 30,
            "best_practice": (
                "Collect continuously inside the vehicle and include at least one "
                "complete stop with the engine in its normal state."
            ),
            "csv_columns": ["x", "y", "z", "timestamp (optional with sample_rate_hz)"],
        },
        "limits": {
            "max_samples": settings.max_samples,
            "max_request_bytes": settings.max_request_bytes,
            "rate_limit_per_minute": settings.rate_limit_per_minute,
        },
        "known_limitations": predictor.artifact["limitations"],
        "links": {
            "docs": str(request.base_url).rstrip("/") + "/docs",
            "redoc": str(request.base_url).rstrip("/") + "/redoc",
            "openapi": str(request.base_url).rstrip("/") + "/openapi.json",
            "github": "https://github.com/tamanna2311/EV-detector",
        },
    }


@router.post(
    "/predict",
    response_model=PredictionResponse,
    responses={422: {"model": ErrorResponse}},
    operation_id="predict_from_json",
    summary="Classify accelerometer samples",
    description=(
        "Submit x/y/z acceleration in m/s². Include timestamps on every sample, "
        "or provide sample_rate_hz."
    ),
    tags=["Prediction"],
)
async def predict_json(
    payload: PredictionRequest, request: Request
) -> PredictionResponse:
    return predict_request(payload, request.app.state.predictor, _request_id(request))


@router.post(
    "/predict/csv",
    response_model=PredictionResponse,
    responses={422: {"model": ErrorResponse}},
    operation_id="predict_from_csv",
    summary="Classify an accelerometer CSV",
    description=(
        "Upload a UTF-8 CSV with x, y, z and optional timestamp columns. "
        "Provide sample_rate_hz when timestamp is omitted."
    ),
    tags=["Prediction"],
)
async def predict_csv(
    request: Request,
    file: Annotated[UploadFile, File(description="Accelerometer CSV, maximum 10 MB.")],
    sample_rate_hz: Annotated[
        float | None, Form(description="Required if timestamp is omitted.")
    ] = None,
    vehicle_stationary: Annotated[
        bool,
        Form(
            description=(
                "True only if the complete recording was captured while stopped."
            )
        ),
    ] = False,
) -> PredictionResponse:
    content = await file.read(settings.max_request_bytes + 1)
    payload = parse_accelerometer_csv(
        content,
        sample_rate_hz=sample_rate_hz,
        vehicle_stationary=vehicle_stationary,
    )
    return predict_request(payload, request.app.state.predictor, _request_id(request))
