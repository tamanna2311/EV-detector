"""Strict, bounded, memory-efficient parsing for accelerometer CSV uploads."""

from __future__ import annotations

import csv
import io
from array import array
from dataclasses import dataclass
from typing import BinaryIO

import numpy as np
from numpy.typing import NDArray

from app.config import settings
from app.ml.features import normalize_timestamps, parse_timestamp_value


class CsvValidationError(ValueError):
    """Raised for invalid uploaded CSV content."""


@dataclass(frozen=True)
class ParsedCsvSignal:
    values: NDArray[np.float64]
    timestamps: NDArray[np.float64] | None
    sample_rate_hz: float | None
    vehicle_stationary: bool

    @property
    def sample_count(self) -> int:
        return len(self.values)


def parse_accelerometer_csv_stream(
    binary_stream: BinaryIO,
    *,
    sample_rate_hz: float | None,
    vehicle_stationary: bool,
) -> ParsedCsvSignal:
    """Parse up to one million rows without constructing per-row model objects."""

    values = array("d")
    raw_timestamps = array("d")
    text_stream = io.TextIOWrapper(
        binary_stream, encoding="utf-8-sig", errors="strict", newline=""
    )
    try:
        reader = csv.DictReader(text_stream)
        columns = {column.strip().lower() for column in (reader.fieldnames or [])}
        required = {"x", "y", "z"}
        if not required.issubset(columns):
            raise CsvValidationError("CSV must contain x, y, and z columns.")

        field_map = {
            column.strip().lower(): column for column in reader.fieldnames or []
        }
        has_timestamp = "timestamp" in field_map
        if not has_timestamp and sample_rate_hz is None:
            raise CsvValidationError(
                "sample_rate_hz is required when CSV timestamp is omitted."
            )

        for row_number, row in enumerate(reader, start=2):
            sample_index = row_number - 2
            if sample_index >= settings.max_csv_samples:
                raise CsvValidationError(
                    f"CSV exceeds the {settings.max_csv_samples:,}-sample limit."
                )
            try:
                values.extend(
                    (
                        float(row[field_map["x"]]),
                        float(row[field_map["y"]]),
                        float(row[field_map["z"]]),
                    )
                )
                if has_timestamp:
                    raw_timestamps.append(
                        parse_timestamp_value(row[field_map["timestamp"]])
                    )
            except (KeyError, TypeError, ValueError) as exc:
                raise CsvValidationError(
                    f"Invalid value on CSV row {row_number}."
                ) from exc
    except UnicodeDecodeError as exc:
        raise CsvValidationError("CSV must be UTF-8 encoded.") from exc
    except csv.Error as exc:
        raise CsvValidationError(f"Malformed CSV: {exc}.") from exc
    finally:
        text_stream.detach()

    sample_count = len(values) // 3
    if sample_count == 0:
        raise CsvValidationError("The uploaded CSV contains no data rows.")

    value_matrix = np.frombuffer(values, dtype=np.float64).reshape(sample_count, 3)
    timestamps = (
        normalize_timestamps(np.frombuffer(raw_timestamps, dtype=np.float64))
        if raw_timestamps
        else None
    )
    return ParsedCsvSignal(
        values=value_matrix,
        timestamps=timestamps,
        sample_rate_hz=sample_rate_hz,
        vehicle_stationary=vehicle_stationary,
    )
