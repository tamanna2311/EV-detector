"""Strict, bounded parsing for accelerometer CSV uploads."""

from __future__ import annotations

import csv
import io

from app.config import settings
from app.schemas import AccelerometerSample, PredictionContext, PredictionRequest


class CsvValidationError(ValueError):
    """Raised for invalid uploaded CSV content."""


def parse_accelerometer_csv(
    content: bytes,
    *,
    sample_rate_hz: float | None,
    vehicle_stationary: bool,
) -> PredictionRequest:
    if not content:
        raise CsvValidationError("The uploaded CSV is empty.")
    if len(content) > settings.max_request_bytes:
        raise CsvValidationError(
            f"CSV exceeds the {settings.max_request_bytes // (1024 * 1024)} MB limit."
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(text))
    columns = {column.strip().lower() for column in (reader.fieldnames or [])}
    required = {"x", "y", "z"}
    if not required.issubset(columns):
        raise CsvValidationError("CSV must contain x, y, and z columns.")

    field_map = {column.strip().lower(): column for column in reader.fieldnames or []}
    has_timestamp = "timestamp" in field_map
    samples: list[AccelerometerSample] = []
    for row_number, row in enumerate(reader, start=2):
        if len(samples) >= settings.max_samples:
            raise CsvValidationError(
                f"CSV exceeds the {settings.max_samples:,}-sample limit."
            )
        try:
            samples.append(
                AccelerometerSample(
                    x=float(row[field_map["x"]]),
                    y=float(row[field_map["y"]]),
                    z=float(row[field_map["z"]]),
                    timestamp=row[field_map["timestamp"]] if has_timestamp else None,
                )
            )
        except (TypeError, ValueError) as exc:
            raise CsvValidationError(f"Invalid value on CSV row {row_number}.") from exc

    try:
        return PredictionRequest(
            samples=samples,
            sample_rate_hz=sample_rate_hz,
            context=PredictionContext(vehicle_stationary=vehicle_stationary),
        )
    except ValueError as exc:
        raise CsvValidationError(str(exc)) from exc
