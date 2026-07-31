# API integration notes

Base path: `/api/v1`

## JSON prediction

`POST /api/v1/predict`

```json
{
  "sample_rate_hz": 200,
  "context": {
    "vehicle_stationary": false
  },
  "samples": [
    {"x": 0.012, "y": -0.021, "z": 9.802}
  ]
}
```

If each sample has a `timestamp`, `sample_rate_hz` may be omitted. Timestamps
must be numeric seconds or `HH:MM:SS[.fraction]`, non-decreasing, and present on
every sample.

## CSV prediction

`POST /api/v1/predict/csv` as multipart form data:

- `file`: UTF-8 CSV
- `sample_rate_hz`: optional number
- `vehicle_stationary`: optional boolean, default `false`

CSV:

```csv
x,y,z,timestamp
1.62495,4.82895,8.02005,07:03:40.01
1.64895,4.86495,8.00805,07:03:40.02
```

CSV uploads support up to 1,000,000 samples or 128 MB, whichever is reached
first. JSON requests remain limited to 100,000 samples.

## Response

```json
{
  "request_id": "04b07f6e-659a-478c-8f1c-735383441d5d",
  "prediction": "EV",
  "ev_probability": 0.985,
  "non_ev_probability": 0.015,
  "confidence": 0.985,
  "decision_quality": "HIGH",
  "needs_more_data": false,
  "caveats": [
    "Stop periods were estimated from the quietest acceleration windows."
  ],
  "model_version": "spectral-logreg-1.0.0",
  "analysis": {
    "samples_received": 36064,
    "samples_analyzed": 35840,
    "segment_count": 1,
    "estimated_sample_rates_hz": [200.372],
    "analyzed_duration_seconds": 178.867,
    "windows_total": 139,
    "windows_selected": 35,
    "median_high_frequency_rms": 0.002,
    "median_peak_to_noise_ratio": 4.2,
    "dominant_frequencies_hz": [19.9, 23.4],
    "out_of_distribution_score": 2.4
  }
}
```

Probabilities describe the classifier output and are not representative-fleet
accuracy estimates. A client should surface `decision_quality`, honor
`needs_more_data`, and never coerce `INCONCLUSIVE` into a binary label.

## Errors

Errors use one stable envelope:

```json
{
  "error": {
    "code": "INVALID_SIGNAL",
    "message": "Sampling rate 40.0 Hz is too low; at least 50 Hz is required.",
    "request_id": "..."
  }
}
```

Expected statuses: `413` request too large, `422` invalid request or signal,
`429` rate limit. `X-Request-ID` is returned on every response.
