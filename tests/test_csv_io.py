from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

import app.csv_io as csv_io
from app.csv_io import CsvValidationError, parse_accelerometer_csv_stream


def test_stream_parser_returns_compact_arrays() -> None:
    content = b"x,y,z,timestamp\n0,0,9.81,10.00\n0.1,0,9.82,10.01\n"
    parsed = parse_accelerometer_csv_stream(
        io.BytesIO(content),
        sample_rate_hz=200,
        vehicle_stationary=True,
    )
    assert parsed.values.shape == (2, 3)
    assert parsed.timestamps is not None
    assert parsed.timestamps.tolist() == [10.0, 10.01]
    assert parsed.vehicle_stationary is True


def test_stream_parser_enforces_csv_sample_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        csv_io,
        "settings",
        SimpleNamespace(max_csv_samples=2),
    )
    content = b"x,y,z\n0,0,9.81\n0,0,9.81\n0,0,9.81\n"
    with pytest.raises(CsvValidationError, match="2-sample limit"):
        parse_accelerometer_csv_stream(
            io.BytesIO(content),
            sample_rate_hz=200,
            vehicle_stationary=False,
        )


def test_stream_parser_requires_rate_without_timestamps() -> None:
    with pytest.raises(CsvValidationError, match="sample_rate_hz"):
        parse_accelerometer_csv_stream(
            io.BytesIO(b"x,y,z\n0,0,9.81\n"),
            sample_rate_hz=None,
            vehicle_stationary=False,
        )
