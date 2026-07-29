"""Dependency-light JSON model loading and trip-level inference."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.ml.features import (
    FEATURE_NAMES,
    RECOMMENDED_SAMPLE_RATE_HZ,
    WindowFeatures,
    select_quiet_windows,
)


@dataclass(frozen=True)
class ModelOutput:
    label: str
    non_ev_probability: float
    confidence: float
    quality: str
    needs_more_data: bool
    selected_indices: NDArray[np.int64]
    caveats: list[str]
    out_of_distribution_score: float


class SpectralPredictor:
    def __init__(self, model_path: Path) -> None:
        with model_path.open(encoding="utf-8") as handle:
            artifact = json.load(handle)
        if artifact["feature_names"] != FEATURE_NAMES:
            raise RuntimeError(
                "Model feature contract does not match application code."
            )
        self.artifact = artifact
        self.version: str = artifact["model_version"]
        self.mean = np.asarray(artifact["scaler"]["mean"], dtype=np.float64)
        self.scale = np.asarray(artifact["scaler"]["scale"], dtype=np.float64)
        self.coefficients = np.asarray(
            artifact["classifier"]["coefficients"], dtype=np.float64
        )
        self.intercept = float(artifact["classifier"]["intercept"])

    def window_probabilities(self, matrix: NDArray[np.float64]) -> NDArray[np.float64]:
        standardized = (matrix - self.mean) / self.scale
        logits = standardized @ self.coefficients + self.intercept
        logits = np.clip(logits, -35, 35)
        return 1.0 / (1.0 + np.exp(-logits))

    def predict(
        self, features: WindowFeatures, known_stationary: bool = False
    ) -> ModelOutput:
        indices = select_quiet_windows(features, known_stationary)
        selected = features.matrix[indices]
        window_probabilities = self.window_probabilities(selected)
        non_ev_probability = float(np.median(window_probabilities))
        confidence = max(non_ev_probability, 1.0 - non_ev_probability)
        max_abs_z = float(np.max(np.abs((selected - self.mean) / self.scale)))

        if 0.40 <= non_ev_probability <= 0.60:
            label = "INCONCLUSIVE"
        else:
            label = "NON_EV" if non_ev_probability > 0.5 else "EV"

        minimum_rate = min(features.sample_rates_hz)
        caveats: list[str] = []
        if not known_stationary:
            caveats.append(
                "Stop periods were estimated from the quietest acceleration windows."
            )
        if minimum_rate < RECOMMENDED_SAMPLE_RATE_HZ:
            caveats.append(
                "Sampling below 100 Hz narrows the detectable vibration spectrum."
            )
        if max_abs_z > 6:
            caveats.append(
                "Some signal features are outside the range represented in training."
            )
        if len(indices) < 8:
            caveats.append("Fewer than eight analysis windows were available.")

        if confidence >= 0.80 and len(indices) >= 8 and max_abs_z <= 6:
            quality = "HIGH" if minimum_rate >= RECOMMENDED_SAMPLE_RATE_HZ else "MEDIUM"
        elif confidence >= 0.65 and len(indices) >= 4:
            quality = "MEDIUM"
        else:
            quality = "LOW"

        needs_more_data = label == "INCONCLUSIVE" or quality == "LOW"
        if needs_more_data:
            caveats.append(
                "Collect at least 30 seconds including a complete vehicle stop "
                "and retry."
            )

        return ModelOutput(
            label=label,
            non_ev_probability=non_ev_probability,
            confidence=confidence,
            quality=quality,
            needs_more_data=needs_more_data,
            selected_indices=indices,
            caveats=caveats,
            out_of_distribution_score=max_abs_z,
        )
