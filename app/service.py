"""Application service that turns validated samples into an API response."""

from __future__ import annotations

from collections import Counter

import numpy as np

from app.ml.features import (
    build_segments,
    extract_window_features,
    normalize_timestamps,
)
from app.ml.predictor import SpectralPredictor
from app.schemas import AnalysisSummary, PredictionRequest, PredictionResponse


def _top_frequencies(values: np.ndarray, limit: int = 5) -> list[float]:
    rounded = np.round(values, 1)
    counts = Counter(float(value) for value in rounded)
    return [frequency for frequency, _ in counts.most_common(limit)]


def predict_request(
    request: PredictionRequest,
    predictor: SpectralPredictor,
    request_id: str,
) -> PredictionResponse:
    values = np.asarray(
        [[sample.x, sample.y, sample.z] for sample in request.samples],
        dtype=np.float64,
    )
    timestamps = (
        normalize_timestamps(
            sample.timestamp
            for sample in request.samples
            if sample.timestamp is not None
        )
        if request.samples[0].timestamp is not None
        else None
    )
    return predict_signal(
        values=values,
        timestamps=timestamps,
        sample_rate_hz=request.sample_rate_hz,
        known_stationary=request.context.vehicle_stationary,
        samples_received=len(request.samples),
        predictor=predictor,
        request_id=request_id,
    )


def predict_signal(
    *,
    values: np.ndarray,
    timestamps: np.ndarray | None,
    sample_rate_hz: float | None,
    known_stationary: bool,
    samples_received: int,
    predictor: SpectralPredictor,
    request_id: str,
) -> PredictionResponse:
    """Predict directly from compact numeric arrays."""

    segments = build_segments(values, timestamps, sample_rate_hz)
    features = extract_window_features(segments)
    output = predictor.predict(features, known_stationary=known_stationary)
    selected = output.selected_indices

    return PredictionResponse(
        request_id=request_id,
        prediction=output.label,
        ev_probability=round(1.0 - output.non_ev_probability, 6),
        non_ev_probability=round(output.non_ev_probability, 6),
        confidence=round(output.confidence, 6),
        decision_quality=output.quality,
        needs_more_data=output.needs_more_data,
        caveats=output.caveats,
        model_version=predictor.version,
        analysis=AnalysisSummary(
            samples_received=samples_received,
            samples_analyzed=features.samples_analyzed,
            segment_count=features.segment_count,
            estimated_sample_rates_hz=[
                round(rate, 3) for rate in features.sample_rates_hz
            ],
            analyzed_duration_seconds=round(features.duration_seconds, 3),
            windows_total=len(features.matrix),
            windows_selected=len(selected),
            median_high_frequency_rms=round(
                float(np.median(features.high_frequency_rms[selected])), 6
            ),
            median_peak_to_noise_ratio=round(
                float(np.median(features.peak_to_noise_ratio[selected])), 3
            ),
            dominant_frequencies_hz=_top_frequencies(
                features.dominant_frequencies_hz[selected]
            ),
            out_of_distribution_score=round(output.out_of_distribution_score, 3),
        ),
    )
