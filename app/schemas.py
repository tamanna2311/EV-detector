"""Versioned public API schemas."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings

FiniteAcceleration = Annotated[float, Field(ge=-200, le=200)]


class AccelerometerSample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: FiniteAcceleration = Field(description="X-axis acceleration in m/s².")
    y: FiniteAcceleration = Field(description="Y-axis acceleration in m/s².")
    z: FiniteAcceleration = Field(description="Z-axis acceleration in m/s².")
    timestamp: float | str | None = Field(
        default=None,
        description="Seconds or HH:MM:SS[.fraction]. Required on every sample if used.",
        examples=["07:03:40.01"],
    )


class PredictionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vehicle_stationary: bool = Field(
        default=False,
        description=(
            "Set true only when every submitted sample was captured while stopped. "
            "Otherwise the service estimates stop candidates."
        ),
    )


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples: list[AccelerometerSample] = Field(
        min_length=128, max_length=settings.max_json_samples
    )
    sample_rate_hz: float | None = Field(
        default=None,
        ge=1,
        le=1000,
        description=(
            "Required if timestamps are omitted; recommended value is at least 100 Hz."
        ),
        examples=[200],
    )
    context: PredictionContext = Field(default_factory=PredictionContext)

    @field_validator("samples")
    @classmethod
    def timestamps_are_all_or_none(
        cls, samples: list[AccelerometerSample]
    ) -> list[AccelerometerSample]:
        present = [sample.timestamp is not None for sample in samples]
        if any(present) and not all(present):
            raise ValueError("timestamp must be provided for every sample or for none.")
        return samples

    @model_validator(mode="after")
    def sampling_information_is_present(self) -> PredictionRequest:
        has_timestamps = bool(self.samples and self.samples[0].timestamp is not None)
        if not has_timestamps and self.sample_rate_hz is None:
            raise ValueError(
                "sample_rate_hz is required when samples do not include timestamps."
            )
        return self


class AnalysisSummary(BaseModel):
    samples_received: int
    samples_analyzed: int
    segment_count: int
    estimated_sample_rates_hz: list[float]
    analyzed_duration_seconds: float
    windows_total: int
    windows_selected: int
    median_high_frequency_rms: float
    median_peak_to_noise_ratio: float
    dominant_frequencies_hz: list[float]
    out_of_distribution_score: float


class PredictionResponse(BaseModel):
    request_id: str
    prediction: Literal["EV", "NON_EV", "INCONCLUSIVE"]
    ev_probability: float = Field(ge=0, le=1)
    non_ev_probability: float = Field(ge=0, le=1)
    confidence: float = Field(
        ge=0,
        le=1,
        description="Model confidence, not a validated real-world accuracy guarantee.",
    )
    decision_quality: Literal["HIGH", "MEDIUM", "LOW"]
    needs_more_data: bool
    caveats: list[str]
    model_version: str
    analysis: AnalysisSummary


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    model_version: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
