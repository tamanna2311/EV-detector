#!/usr/bin/env python3
"""Train, cross-file evaluate, and export the portable JSON model."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix
from sklearn.preprocessing import StandardScaler

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from app.ml.features import (  # noqa: E402
    FEATURE_NAMES,
    build_segments,
    extract_window_features,
    normalize_timestamps,
    select_quiet_windows,
)

MODEL_VERSION = "spectral-logreg-1.0.0"


def load_csv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    values: list[list[float]] = []
    timestamps: list[str] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"x", "y", "z", "timestamp"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"{path} must contain columns: {sorted(required)}")
        for row in reader:
            values.append([float(row["x"]), float(row["y"]), float(row["z"])])
            timestamps.append(row["timestamp"])
    return np.asarray(values, dtype=np.float64), normalize_timestamps(timestamps)


def recording(path: Path) -> dict:
    values, timestamps = load_csv(path)
    segments = build_segments(values, timestamps, sample_rate_hz=None)
    features = extract_window_features(segments)
    return {
        "name": path.name,
        "label": 1 if path.name.lower().startswith("non_ev") else 0,
        "features": features,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def training_arrays(records: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix = np.vstack([item["features"].matrix for item in records])
    labels = np.concatenate(
        [np.full(len(item["features"].matrix), item["label"]) for item in records]
    )
    weights = np.empty(len(labels), dtype=np.float64)
    for label in (0, 1):
        class_records = [item for item in records if item["label"] == label]
        positions = [
            index for index, item in enumerate(records) if item["label"] == label
        ]
        for record_index in positions:
            start = sum(len(item["features"].matrix) for item in records[:record_index])
            size = len(records[record_index]["features"].matrix)
            weights[start : start + size] = 1.0 / (2 * len(class_records) * size)
    return matrix, labels, weights * len(labels)


def fit(records: list[dict]) -> tuple[StandardScaler, LogisticRegression]:
    matrix, labels, weights = training_arrays(records)
    scaler = StandardScaler().fit(matrix, sample_weight=weights)
    transformed = scaler.transform(matrix)
    classifier = LogisticRegression(C=0.1, max_iter=2000, random_state=42)
    classifier.fit(transformed, labels, sample_weight=weights)
    return scaler, classifier


def trip_probability(
    scaler: StandardScaler,
    classifier: LogisticRegression,
    features,
) -> float:
    indices = select_quiet_windows(features, known_stationary=False)
    probabilities = classifier.predict_proba(
        scaler.transform(features.matrix[indices])
    )[:, 1]
    return float(np.median(probabilities))


def evaluate(train_records: list[dict], test_records: list[dict]) -> dict:
    rows: list[dict] = []
    for held_out in [item for item in train_records if item["label"] == 1]:
        fold_records = [item for item in train_records if item is not held_out]
        scaler, classifier = fit(fold_records)
        probability = trip_probability(scaler, classifier, held_out["features"])
        rows.append(
            {
                "file": held_out["name"],
                "true_label": "NON_EV",
                "evaluation": "leave-one-non-ev-recording-out",
                "non_ev_probability": probability,
                "predicted_label": "NON_EV" if probability >= 0.5 else "EV",
            }
        )

    scaler, classifier = fit(train_records)
    for item in test_records:
        probability = trip_probability(scaler, classifier, item["features"])
        rows.append(
            {
                "file": item["name"],
                "true_label": "NON_EV" if item["label"] else "EV",
                "evaluation": "independent-test-folder",
                "non_ev_probability": probability,
                "predicted_label": "NON_EV" if probability >= 0.5 else "EV",
            }
        )

    true = np.asarray([row["true_label"] == "NON_EV" for row in rows])
    predicted = np.asarray([row["predicted_label"] == "NON_EV" for row in rows])
    return {
        "method": (
            "Each non-EV file is scored by a model that excluded it; EV test-folder "
            "files are scored by the final train-folder-only model."
        ),
        "file_level_rows": rows,
        "file_level_confusion_matrix_ev_non_ev": confusion_matrix(
            true, predicted, labels=[False, True]
        ).tolist(),
        "file_level_balanced_accuracy": balanced_accuracy_score(true, predicted),
        "warning": (
            "Only 7 recordings were supplied (1 train EV, 3 train non-EV, "
            "3 test EV). This result is a pipeline check, not a population-level "
            "accuracy estimate."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-dir", type=Path, required=True)
    parser.add_argument("--test-dir", type=Path)
    parser.add_argument(
        "--output", type=Path, default=REPOSITORY_ROOT / "model" / "model.json"
    )
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=REPOSITORY_ROOT / "model" / "evaluation.json",
    )
    args = parser.parse_args()

    train_records = [recording(path) for path in sorted(args.train_dir.glob("*.csv"))]
    if not train_records or {item["label"] for item in train_records} != {0, 1}:
        raise SystemExit("Training directory must contain ev_*.csv and non_ev_*.csv.")
    test_records = (
        [recording(path) for path in sorted(args.test_dir.glob("*.csv"))]
        if args.test_dir
        else []
    )
    scaler, classifier = fit(train_records)
    evaluation = evaluate(train_records, test_records) if test_records else {}

    artifact = {
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "method": "paper-inspired FFT features plus regularized logistic regression",
        "positive_class": "NON_EV",
        "feature_names": FEATURE_NAMES,
        "scaler": {
            "mean": scaler.mean_.tolist(),
            "scale": scaler.scale_.tolist(),
        },
        "classifier": {
            "type": "logistic_regression",
            "coefficients": classifier.coef_[0].tolist(),
            "intercept": float(classifier.intercept_[0]),
            "regularization_c": 0.1,
        },
        "training_data": [
            {
                "file": item["name"],
                "label": "NON_EV" if item["label"] else "EV",
                "windows": len(item["features"].matrix),
                "sha256": item["sha256"],
            }
            for item in train_records
        ],
        "limitations": [
            "The supplied training set has only one EV and three non-EV recordings.",
            (
                "The model detects combustion-engine vibration; hybrids and "
                "engine auto-stop can confuse it."
            ),
            (
                "Predictions require stop or near-stop periods and at least "
                "50 Hz sampling."
            ),
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    args.metrics_output.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_output.write_text(
        json.dumps(evaluation, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(evaluation, indent=2))


if __name__ == "__main__":
    main()
