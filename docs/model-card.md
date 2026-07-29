# Model card: spectral-logreg-1.0.0

## Intended use

Classify a smartphone accelerometer recording as `EV`, `NON_EV`, or
`INCONCLUSIVE` by detecting the stable high-frequency vibration signature of a
combustion engine. It is intended for prototyping, research, and non-critical
mobility analytics.

It is not validated for safety decisions, emissions enforcement, billing,
insurance, legal evidence, or any decision about a person.

## Method

The model is inspired by Wüstenberg et al., *Distinguishing Electric Vehicles
from Fossil-Fueled Vehicles with Mobile Sensing* (2014).

- Signal: `sqrt(x² + y² + z²)`
- Windows: 2.56 seconds, 50% overlap, linear detrending, Hann taper
- Spectrum: real FFT, 19 Hz to the smaller of 80 Hz and 45% of sample rate
- Features: high-frequency RMS, maximum and 95th percentile amplitude,
  peak-to-median ratio, robust spike fraction, spectral entropy, low-frequency
  RMS, and high/low energy ratio
- Classifier: standardized logistic regression (`C=0.1`)
- Trip aggregation: median non-EV probability over known-stop windows or the
  quietest 25% of windows

The original paper used sensor-specific absolute noise floors. Because the
supplied files do not include a device calibration capture, this model also
uses relative peak/noise and spectral-shape features.

## Supplied data audit

| Split | EV recordings | Non-EV recordings | Rows | Observed rate |
| --- | ---: | ---: | ---: | --- |
| Train | 1 | 3 | 144,185 | about 200 Hz |
| Test | 3 | 0 | 84,958 | about 125 or 200 Hz |

One test file contains a roughly 703-second discontinuity. The pipeline splits
this gap and ignores the final fragment because it is shorter than one analysis
window.

The training non-EV recordings show strong high-frequency peaks and the
training EV is near its noise floor, consistent with the paper. The test EV
recordings include substantially more low-frequency movement, so automatic
stop-candidate selection is necessary.

## Evaluation protocol and result

The six reported file predictions are independent with respect to the file:

- Three non-EV predictions come from leave-one-non-EV-recording-out models.
- Three EV predictions come from the final model trained only on `train_data`.

All 3 EV and all 3 non-EV files are classified correctly. This result has
extreme statistical uncertainty because there are only six evaluated
recordings and the supplied test folder contains no non-EV. It must not be
presented as 100% expected real-world accuracy.

The original paper reported 91.6% overall accuracy across eight FFVs, two EVs,
six placements, and independently collected trips. That paper result describes
its dataset and implementation, not this deployment.

## Known failure modes

- Hybrid vehicles when the combustion engine is off
- Automatic engine stop/start while stationary
- Trips without any stop or near-stop period
- Loud bass, strong fans, road vibration, or other stable vibration sources
- Very well isolated combustion engines with attenuated cabin vibration
- Sample rates below 50 Hz or inaccurate sample-rate metadata
- Different sensor gains, units, clipping, filtering, placements, and devices
- Motorcycles, buses, trucks, trains, and other classes outside the target scope

## Decision and confidence semantics

`confidence` is distance from the model's binary boundary after trip
aggregation. It is not calibrated against a representative fleet and is not an
accuracy guarantee. `decision_quality` also incorporates sample rate, window
count, and feature distance from the training distribution. Consumers should
retry low-quality and `INCONCLUSIVE` results.

## Minimum path to a production-validated model

Collect at least dozens of distinct vehicles per class, including hybrids and
auto-stop FFVs, with multiple phone models, placements, roads, temperatures,
audio/fan conditions, and repeated trips. Split by vehicle—not by window or
trip—so no vehicle appears in more than one of train, validation, and test.
Pre-register the target metrics, report class-specific recall and calibrated
uncertainty, and maintain a shadow-mode drift evaluation before acting on
predictions.
