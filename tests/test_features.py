from __future__ import annotations

import numpy as np
import pytest

from app.ml.features import (
    SignalValidationError,
    build_segments,
    extract_window_features,
    normalize_timestamps,
)


def test_timestamp_gap_is_split_and_short_tail_is_ignored() -> None:
    rate = 125
    first = np.arange(0, 5, 1 / rate)
    short_tail = np.arange(0, 0.5, 1 / rate) + 100
    timestamps = np.concatenate([first, short_tail])
    values = np.column_stack(
        [
            np.zeros(len(timestamps)),
            np.zeros(len(timestamps)),
            np.full(len(timestamps), 9.81),
        ]
    )
    segments = build_segments(values, timestamps, sample_rate_hz=None)
    assert len(segments) == 1
    assert segments[0].sample_rate_hz == pytest.approx(125, rel=0.01)
    assert len(extract_window_features(segments).matrix) >= 2


def test_clock_timestamp_midnight_unwrap() -> None:
    result = normalize_timestamps(["23:59:59.99", "00:00:00.00", "00:00:00.01"])
    assert np.all(np.diff(result) >= 0)
    assert result[-1] - result[0] == pytest.approx(0.02)


def test_numeric_string_timestamps() -> None:
    result = normalize_timestamps(["10.0", "10.5", "11.0"])
    assert result.tolist() == [10.0, 10.5, 11.0]


def test_bad_units_are_rejected() -> None:
    values = np.zeros((512, 3))
    values[0, 0] = 999
    with pytest.raises(SignalValidationError, match="supported"):
        build_segments(values, None, sample_rate_hz=200)
