from __future__ import annotations

import csv
import io
import math
import random

from fastapi.testclient import TestClient


def samples(*, combustion: bool, seconds: float = 12, rate: int = 200) -> list[dict]:
    rng = random.Random(42)
    output = []
    for index in range(round(seconds * rate)):
        time = index / rate
        vibration = (
            0.50 * math.sin(2 * math.pi * 28 * time)
            + 0.25 * math.sin(2 * math.pi * 56 * time)
            if combustion
            else 0
        )
        output.append(
            {
                "x": rng.gauss(0, 0.008),
                "y": rng.gauss(0, 0.008),
                "z": 9.81 + rng.gauss(0, 0.008) + vibration,
            }
        )
    return output


def test_health_and_metadata(client: TestClient) -> None:
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["x-request-id"]

    metadata = client.get("/api/v1/meta")
    assert metadata.status_code == 200
    assert metadata.json()["collection"]["recommended_sample_rate_hz"] == 100
    assert metadata.json()["limits"]["max_csv_samples"] == 1_000_000
    assert metadata.json()["limits"]["max_json_samples"] == 100_000
    assert metadata.json()["limits"]["max_request_bytes"] == 128 * 1024 * 1024


def test_json_predictions_separate_synthetic_signals(client: TestClient) -> None:
    ev = client.post(
        "/api/v1/predict",
        json={"sample_rate_hz": 200, "samples": samples(combustion=False)},
    )
    non_ev = client.post(
        "/api/v1/predict",
        json={"sample_rate_hz": 200, "samples": samples(combustion=True)},
    )
    assert ev.status_code == 200, ev.text
    assert non_ev.status_code == 200, non_ev.text
    assert ev.json()["prediction"] == "EV"
    assert non_ev.json()["prediction"] == "NON_EV"


def test_csv_upload(client: TestClient) -> None:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=["x", "y", "z"])
    writer.writeheader()
    writer.writerows(samples(combustion=False, seconds=5))
    response = client.post(
        "/api/v1/predict/csv",
        files={"file": ("recording.csv", stream.getvalue(), "text/csv")},
        data={"sample_rate_hz": "200", "vehicle_stationary": "true"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["analysis"]["samples_received"] == 1000


def test_low_sampling_rate_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/predict",
        json={"sample_rate_hz": 40, "samples": samples(combustion=False, rate=40)},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SIGNAL"


def test_partial_timestamps_are_rejected(client: TestClient) -> None:
    signal = samples(combustion=False, seconds=3)
    signal[0]["timestamp"] = 0
    response = client.post("/api/v1/predict", json={"samples": signal})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
