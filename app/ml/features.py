"""Paper-inspired accelerometer feature extraction.

The detector operates on the orientation-independent acceleration magnitude,
uses 2.56 second Hann-windowed FFTs, and emphasizes stable energy above 19 Hz.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import ceil

import numpy as np
from numpy.typing import NDArray

WINDOW_SECONDS = 2.56
WINDOW_OVERLAP = 0.5
HIGH_PASS_HZ = 19.0
MAX_ANALYSIS_HZ = 80.0
MIN_SAMPLE_RATE_HZ = 50.0
RECOMMENDED_SAMPLE_RATE_HZ = 100.0
GAP_SECONDS = 0.10

FEATURE_NAMES = [
    "log_hf_rms",
    "log_hf_max",
    "log_hf_p95",
    "log_peak_to_median",
    "spike_fraction",
    "spectral_entropy",
    "log_low_frequency_rms",
    "log_high_to_low_ratio",
]


class SignalValidationError(ValueError):
    """Raised when a signal cannot support a trustworthy prediction."""


@dataclass(frozen=True)
class SignalSegment:
    values: NDArray[np.float64]
    sample_rate_hz: float
    duration_seconds: float


@dataclass(frozen=True)
class WindowFeatures:
    matrix: NDArray[np.float64]
    dominant_frequencies_hz: NDArray[np.float64]
    high_frequency_rms: NDArray[np.float64]
    peak_to_noise_ratio: NDArray[np.float64]
    segment_count: int
    samples_analyzed: int
    duration_seconds: float
    sample_rates_hz: tuple[float, ...]


def _clock_seconds(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise SignalValidationError(
            "Timestamps must be seconds or HH:MM:SS[.fraction]."
        )
    try:
        hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
    except ValueError as exc:
        raise SignalValidationError(f"Invalid timestamp: {value!r}.") from exc
    if not (0 <= hours <= 23 and 0 <= minutes <= 59 and 0 <= seconds < 60):
        raise SignalValidationError(f"Invalid timestamp: {value!r}.")
    return hours * 3600 + minutes * 60 + seconds


def normalize_timestamps(values: Iterable[str | float | int]) -> NDArray[np.float64]:
    """Parse numeric or clock timestamps and unwrap a midnight crossing."""

    parsed: list[float] = []
    for value in values:
        try:
            if isinstance(value, str) and ":" in value:
                parsed.append(_clock_seconds(value))
            else:
                parsed.append(float(value))
        except (TypeError, ValueError) as exc:
            raise SignalValidationError(f"Invalid timestamp: {value!r}.") from exc

    result = np.asarray(parsed, dtype=np.float64)
    if not np.all(np.isfinite(result)):
        raise SignalValidationError("Timestamps must all be finite.")

    day_offset = 0.0
    for index in range(1, len(result)):
        candidate = result[index] + day_offset
        if candidate < result[index - 1]:
            if result[index - 1] - candidate > 12 * 3600:
                day_offset += 24 * 3600
                candidate = result[index] + day_offset
            else:
                raise SignalValidationError("Timestamps must be non-decreasing.")
        result[index] = candidate
    return result


def build_segments(
    values: NDArray[np.float64],
    timestamps: NDArray[np.float64] | None,
    sample_rate_hz: float | None,
) -> list[SignalSegment]:
    """Split gaps and infer the effective rate from sample count and duration."""

    if values.ndim != 2 or values.shape[1] != 3:
        raise SignalValidationError("Accelerometer values must have shape (n, 3).")
    if len(values) < 128:
        raise SignalValidationError("At least 128 accelerometer samples are required.")
    if not np.all(np.isfinite(values)):
        raise SignalValidationError("Accelerometer values must all be finite.")
    if np.max(np.abs(values)) > 200:
        raise SignalValidationError(
            "Acceleration exceeds the supported ±200 m/s² range; check units."
        )
    if sample_rate_hz is not None and not 1 <= sample_rate_hz <= 1000:
        raise SignalValidationError("sample_rate_hz must be between 1 and 1000.")

    if timestamps is None:
        if sample_rate_hz is None:
            raise SignalValidationError(
                "Provide sample_rate_hz when samples do not include timestamps."
            )
        groups = [np.arange(len(values))]
    else:
        if len(timestamps) != len(values):
            raise SignalValidationError(
                "Every sample must have a timestamp when timestamp inference is used."
            )
        deltas = np.diff(timestamps)
        threshold = (
            max(GAP_SECONDS, 5.0 / sample_rate_hz) if sample_rate_hz else GAP_SECONDS
        )
        groups = np.split(np.arange(len(values)), np.where(deltas > threshold)[0] + 1)

    segments: list[SignalSegment] = []
    for indices in groups:
        if len(indices) < 128:
            continue
        rate = sample_rate_hz
        duration: float
        if timestamps is not None:
            duration = float(timestamps[indices[-1]] - timestamps[indices[0]])
            if duration <= 0:
                continue
            inferred_rate = (len(indices) - 1) / duration
            if rate is None:
                rate = inferred_rate
            elif abs(inferred_rate - rate) / rate > 0.20:
                raise SignalValidationError(
                    "sample_rate_hz differs from the timestamp-derived rate by "
                    "more than 20%."
                )
        else:
            assert rate is not None
            duration = (len(indices) - 1) / rate

        assert rate is not None
        if rate < MIN_SAMPLE_RATE_HZ:
            raise SignalValidationError(
                f"Sampling rate {rate:.1f} Hz is too low; at least "
                f"{MIN_SAMPLE_RATE_HZ:.0f} Hz is required."
            )
        required = max(128, round(WINDOW_SECONDS * rate))
        if len(indices) >= required:
            segments.append(
                SignalSegment(
                    values=values[indices],
                    sample_rate_hz=float(rate),
                    duration_seconds=duration,
                )
            )

    if not segments:
        raise SignalValidationError(
            "No continuous segment is long enough for a 2.56-second analysis window."
        )
    return segments


def _linear_detrend(values: NDArray[np.float64]) -> NDArray[np.float64]:
    x = np.arange(len(values), dtype=np.float64)
    centered_x = x - x.mean()
    slope = float(centered_x @ (values - values.mean()) / (centered_x @ centered_x))
    return values - (values.mean() + slope * centered_x)


def extract_window_features(segments: list[SignalSegment]) -> WindowFeatures:
    rows: list[list[float]] = []
    dominant_frequencies: list[float] = []
    hf_rms_values: list[float] = []
    peak_ratios: list[float] = []
    samples_analyzed = 0
    duration_seconds = 0.0

    for segment in segments:
        rate = segment.sample_rate_hz
        window_size = max(128, round(WINDOW_SECONDS * rate))
        hop = max(1, round(window_size * (1 - WINDOW_OVERLAP)))
        window = np.hanning(window_size)
        magnitude = np.linalg.norm(segment.values, axis=1)
        used_samples = 0

        for start in range(0, len(magnitude) - window_size + 1, hop):
            detrended = _linear_detrend(magnitude[start : start + window_size])
            spectrum = np.abs(np.fft.rfft(detrended * window)) * 2 / window.sum()
            frequencies = np.fft.rfftfreq(window_size, d=1.0 / rate)
            upper_hz = min(MAX_ANALYSIS_HZ, rate * 0.45)
            high_mask = (frequencies >= HIGH_PASS_HZ) & (frequencies <= upper_hz)
            low_mask = (frequencies >= 0.5) & (frequencies < 10.0)
            if np.count_nonzero(high_mask) < 5:
                continue

            high = spectrum[high_mask]
            low = spectrum[low_mask]
            median = float(np.median(high))
            mad = float(np.median(np.abs(high - median))) + 1e-9
            power = np.square(high)
            normalized_power = power / max(float(power.sum()), 1e-12)
            entropy = float(
                -np.sum(normalized_power * np.log(normalized_power + 1e-12))
                / np.log(len(normalized_power))
            )
            hf_rms = float(np.sqrt(np.mean(power)))
            low_rms = float(np.sqrt(np.mean(np.square(low)))) if len(low) else 0.0
            peak_index = int(np.argmax(high))
            peak_ratio = float(high[peak_index] / (median + 1e-9))

            rows.append(
                [
                    np.log1p(hf_rms * 100),
                    np.log1p(float(np.max(high)) * 100),
                    np.log1p(float(np.quantile(high, 0.95)) * 100),
                    np.log1p(peak_ratio),
                    float(np.mean(high > median + 8 * mad)),
                    entropy,
                    np.log1p(low_rms * 100),
                    np.log1p(hf_rms / (low_rms + 1e-9)),
                ]
            )
            dominant_frequencies.append(float(frequencies[high_mask][peak_index]))
            hf_rms_values.append(hf_rms)
            peak_ratios.append(peak_ratio)
            used_samples = max(used_samples, start + window_size)

        samples_analyzed += used_samples
        duration_seconds += used_samples / rate

    if not rows:
        raise SignalValidationError(
            "No FFT windows could be extracted from the signal."
        )

    return WindowFeatures(
        matrix=np.asarray(rows, dtype=np.float64),
        dominant_frequencies_hz=np.asarray(dominant_frequencies, dtype=np.float64),
        high_frequency_rms=np.asarray(hf_rms_values, dtype=np.float64),
        peak_to_noise_ratio=np.asarray(peak_ratios, dtype=np.float64),
        segment_count=len(segments),
        samples_analyzed=samples_analyzed,
        duration_seconds=duration_seconds,
        sample_rates_hz=tuple(segment.sample_rate_hz for segment in segments),
    )


def select_quiet_windows(
    features: WindowFeatures, known_stationary: bool
) -> NDArray[np.int64]:
    """Use all known-stop windows, otherwise choose the quietest quarter."""

    count = len(features.matrix)
    if known_stationary:
        return np.arange(count, dtype=np.int64)
    selected_count = min(count, max(8, ceil(0.25 * count)))
    activity_column = FEATURE_NAMES.index("log_low_frequency_rms")
    return np.argsort(features.matrix[:, activity_column])[:selected_count]
