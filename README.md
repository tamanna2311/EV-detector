# EV Detector

Production-oriented EV vs non-EV classification from smartphone accelerometer
recordings. The service uses orientation-independent spectral features to look
for combustion-engine vibration during stopped or near-stopped periods.

The mobile-first PWA can record accelerometer data directly on supported phones.
It requests motion permission only after the user taps Start, prefers the
high-resolution Generic Sensor API where available, and falls back to
`DeviceMotionEvent` on browsers such as mobile Safari. The installed app shell
works offline; prediction still requires a network connection to the API.

For higher-rate collection, the repository also includes a native Android app
under [`android/`](android/). It requests 200 Hz directly through
`SensorManager`, records monotonic nanosecond sensor timestamps, reports the
actual achieved rate, writes the API-compatible CSV locally, and submits it to
the production prediction endpoint. The app stops collection if it leaves the
foreground and requires an explicit safely-stopped confirmation.

> **Evidence boundary:** the supplied dataset contains only seven recordings:
> one EV and three non-EVs for training, and three EVs for testing. The checked-in
> evaluation verifies that this pipeline separates those recordings; it does not
> establish population-level accuracy. Collect a larger, vehicle-grouped dataset
> before using the result for safety-critical, regulatory, or financial decisions.

## Links

- Live app: <https://ev-detector.onrender.com>
- Swagger UI: <https://ev-detector.onrender.com/docs>
- ReDoc: <https://ev-detector.onrender.com/redoc>
- OpenAPI: <https://ev-detector.onrender.com/openapi.json>
- GitHub: <https://github.com/tamanna2311/EV-detector>
- Render dashboard:
  <https://dashboard.render.com/web/srv-d9km0ij7uimc73fkmp60>

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Liveness and model readiness |
| `GET` | `/api/v1/meta` | Model contract, limits, and collection guidance |
| `POST` | `/api/v1/predict` | Predict from JSON accelerometer samples |
| `POST` | `/api/v1/predict/csv` | Predict from an uploaded CSV |

JSON example:

```bash
curl -X POST http://localhost:8000/api/v1/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "sample_rate_hz": 200,
    "context": {"vehicle_stationary": false},
    "samples": [
      {"x": 0.01, "y": 0.02, "z": 9.80}
    ]
  }'
```

The example is abbreviated. At least one continuous 2.56-second window is
required; 30 seconds including a stop is recommended.

CSV upload:

```bash
curl -X POST http://localhost:8000/api/v1/predict/csv \
  -F 'file=@recording.csv' \
  -F 'vehicle_stationary=false'
```

Use `-F 'sample_rate_hz=200'` when the CSV does not include `timestamp`.

## Data contract

- CSV columns: `x,y,z,timestamp`
- Units: metres per second squared (`m/s²`)
- Timestamp: numeric seconds or `HH:MM:SS[.fraction]`
- Minimum sample rate: 50 Hz
- Recommended sample rate: 100–200 Hz
- Maximum CSV: 128 MB and 1,000,000 samples
- Maximum JSON: 1,000,000 samples
- Best recording: at least 30 seconds with one complete stop

Both JSON and CSV accept up to 1,000,000 samples, subject to the shared 128 MB
request limit. CSV is the more memory-efficient choice for very large
recordings because it is parsed into compact numeric arrays; JSON is intended
for direct application integration and uses the structured request contract
shown above. The service splits timestamp gaps, infers the sample rate per
continuous segment, rejects incompatible inputs, and returns `INCONCLUSIVE`
rather than forcing a binary answer near the decision boundary.

## How the model maps to the paper

The implementation follows *Distinguishing Electric Vehicles from
Fossil-Fueled Vehicles with Mobile Sensing*:

1. Transform x/y/z into acceleration magnitude for orientation independence.
2. Analyze overlapping 2.56-second windows.
3. Apply a Hann window and real FFT.
4. Focus on frequencies above the paper's empirical 19 Hz cut-off.
5. Extract peak, noise-floor, energy, and spectral-stability features.
6. Aggregate the quietest windows as stop candidates when stops are not labeled.
7. Classify with regularized logistic regression and aggregate by median window
   probability.

The repository adds the parts needed by the supplied data and an online API:
sample-rate inference, a 703-second-gap split, support for both ~125 Hz and
~200 Hz signals, bounded input validation, decision-quality flags, and
out-of-distribution reporting.

## Evaluation

The generated [`model/evaluation.json`](model/evaluation.json) uses an
independent-by-recording protocol:

- Each of the three non-EV training files is scored by a fold model that did
  not train on that file.
- The final train-folder-only model scores the three EV files in the test
  folder.

All six independently scored files are classified correctly. This is useful
as a pipeline check, but the sample size is far too small for a trustworthy
accuracy estimate or confidence interval. See
[`docs/model-card.md`](docs/model-card.md) for limitations and the next data
collection milestone.

## Local development

Python 3.13 is used in CI and the container.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload
```

Open <http://localhost:8000>, <http://localhost:8000/docs>, or
<http://localhost:8000/redoc>.

### Native Android collector

Requirements: JDK 17 and Android SDK platform 36.

```bash
cd android
./gradlew testDebugUnitTest lintDebug assembleDebug
```

The installable development APK is written to
`android/app/build/outputs/apk/debug/app-debug.apk`. The Android build is also
published as a downloadable artifact by GitHub Actions. Exactly 200 Hz is
requested using a 5,000 microsecond sampling period, but the UI always reports
the achieved hardware rate because Android treats the requested period as a
hint.

Install the development build on a USB-connected phone with:

```bash
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

For a signed release, provide `EVTRACE_KEYSTORE_PATH`,
`EVTRACE_KEYSTORE_PASSWORD`, `EVTRACE_KEY_ALIAS`, and `EVTRACE_KEY_PASSWORD`,
then run `./gradlew assembleRelease`. Signing credentials and keystores must
remain outside the repository.

## Re-training

Raw recordings are deliberately not committed. Filenames provide labels:
`ev_*.csv` and `non_ev_*.csv`.

```bash
python scripts/train_model.py \
  --train-dir /path/to/train_data \
  --test-dir /path/to/test_data
```

The script writes a portable JSON model (no pickle execution risk), data
fingerprints, and evaluation results. Keep the test folder untouched until the
final evaluation.

## Production

### Docker

```bash
docker build -t ev-detector .
docker run --rm -p 10000:10000 ev-detector
```

The image runs as a non-root user and includes an application health check.

### Render

The repository includes [`render.yaml`](render.yaml). Create a Render Blueprint
from the repository, or create a Docker web service with:

- Health check: `/api/v1/health`
- Port: supplied by Render through `PORT`
- Auto-deploy: enabled

Configuration is environment-based; see [`.env.example`](.env.example).

## Operational safeguards

- Strict schemas and acceleration-unit bounds
- Request-size and sample-count limits
- Per-client rate limiting
- Request IDs in responses and logs
- Security headers, trusted hosts, explicit CORS configuration, and gzip
- No raw sensor data persistence
- Portable non-executable model artifact
- Health endpoint, Docker health check, tests, linting, coverage, and CI build

For a horizontally scaled deployment, replace the in-process rate limiter with
Redis or an API gateway. For model monitoring, log consented aggregate features
and outcomes—not raw sensor traces—and track device/vehicle-group drift.

## License

MIT. The referenced paper and user-supplied datasets retain their original
rights and are not redistributed by this repository.
