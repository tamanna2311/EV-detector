(() => {
  "use strict";

  const MAX_LIVE_SAMPLES = 100_000;
  const RECOMMENDED_SECONDS = 30;
  const MINIMUM_SAMPLES = 128;
  const MINIMUM_RATE_HZ = 50;

  const elements = {
    canvas: document.getElementById("signal-canvas"),
    streamLabel: document.getElementById("stream-label"),
    liveDot: document.getElementById("live-dot"),
    sensorSupport: document.getElementById("sensor-support"),
    safety: document.getElementById("safety-confirmation"),
    start: document.getElementById("start-recording"),
    stop: document.getElementById("stop-recording"),
    console: document.getElementById("recording-console"),
    state: document.getElementById("recording-state"),
    duration: document.getElementById("duration-value"),
    samples: document.getElementById("sample-value"),
    rate: document.getElementById("rate-value"),
    progress: document.getElementById("duration-progress"),
    hint: document.getElementById("recording-hint"),
    liveResult: document.getElementById("live-result"),
    uploadForm: document.getElementById("upload-form"),
    uploadSubmit: document.getElementById("upload-submit"),
    uploadResult: document.getElementById("upload-result"),
    file: document.getElementById("file"),
    fileDrop: document.getElementById("file-drop"),
    fileName: document.getElementById("file-name"),
    fileDetail: document.getElementById("file-detail"),
    install: document.getElementById("install-button"),
    toast: document.getElementById("toast"),
  };

  const state = {
    samples: [],
    recentMagnitudes: [],
    recording: false,
    analyzing: false,
    startedAt: 0,
    lastTimestamp: 0,
    source: "",
    sensor: null,
    timer: null,
    noDataTimer: null,
    installPrompt: null,
  };

  const supportsMotion =
    window.isSecureContext &&
    ("Accelerometer" in window || "DeviceMotionEvent" in window);

  function formatDuration(seconds) {
    const total = Math.max(0, Math.floor(seconds));
    return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
  }

  function elapsedSeconds() {
    return state.startedAt ? (performance.now() - state.startedAt) / 1000 : 0;
  }

  function achievedRate() {
    if (state.samples.length < 2 || state.lastTimestamp <= 0) return 0;
    return (state.samples.length - 1) / state.lastTimestamp;
  }

  function setToast(message, timeout = 5200) {
    elements.toast.textContent = message;
    elements.toast.hidden = false;
    window.clearTimeout(setToast.timeout);
    setToast.timeout = window.setTimeout(() => {
      elements.toast.hidden = true;
    }, timeout);
  }

  function setSensorSupport() {
    if (!window.isSecureContext) {
      elements.sensorSupport.textContent = "HTTPS required";
      elements.sensorSupport.classList.add("is-unavailable");
      elements.hint.textContent =
        "Motion sensors are available only from the secure HTTPS app.";
      return;
    }
    if (!supportsMotion) {
      elements.sensorSupport.textContent = "Sensor unavailable";
      elements.sensorSupport.classList.add("is-unavailable");
      elements.hint.textContent =
        "This browser does not expose a motion sensor. You can still upload a CSV.";
      return;
    }
    elements.sensorSupport.textContent = "Sensor supported";
    elements.sensorSupport.classList.add("is-ready");
    elements.start.disabled = !elements.safety.checked;
  }

  function updateControls() {
    elements.start.disabled =
      !supportsMotion ||
      !elements.safety.checked ||
      state.recording ||
      state.analyzing;
    elements.stop.disabled = !state.recording || state.analyzing;
  }

  function updateStats() {
    const seconds = state.recording ? elapsedSeconds() : state.lastTimestamp;
    const rate = achievedRate();
    elements.duration.textContent = formatDuration(seconds);
    elements.samples.textContent = state.samples.length.toLocaleString();
    elements.rate.textContent = rate ? `${rate.toFixed(1)} Hz` : "— Hz";
    elements.progress.style.width = `${Math.min(100, (seconds / RECOMMENDED_SECONDS) * 100)}%`;

    if (state.recording) {
      if (seconds < RECOMMENDED_SECONDS) {
        elements.hint.textContent = `Keep the phone still for ${Math.ceil(RECOMMENDED_SECONDS - seconds)} more seconds for the recommended capture.`;
      } else {
        elements.hint.textContent =
          "Recommended duration reached. You can stop and analyze now.";
      }
    }
  }

  function appendSample(x, y, z, timestamp) {
    if (!state.recording) return;
    if (![x, y, z, timestamp].every(Number.isFinite)) return;
    if (state.samples.length >= MAX_LIVE_SAMPLES) {
      stopAndAnalyze();
      return;
    }
    state.lastTimestamp = Math.max(0, timestamp);
    state.samples.push([x, y, z, state.lastTimestamp]);
    const magnitude = Math.hypot(x, y, z);
    state.recentMagnitudes.push(magnitude);
    if (state.recentMagnitudes.length > 240) state.recentMagnitudes.shift();
  }

  function handleDeviceMotion(event) {
    const acceleration = event.accelerationIncludingGravity || event.acceleration;
    if (!acceleration) return;
    appendSample(
      Number(acceleration.x),
      Number(acceleration.y),
      Number(acceleration.z),
      elapsedSeconds(),
    );
  }

  function stopSensorSource() {
    if (state.sensor) {
      state.sensor.stop();
      state.sensor = null;
    }
    window.removeEventListener("devicemotion", handleDeviceMotion);
    window.clearInterval(state.timer);
    window.clearTimeout(state.noDataTimer);
    state.timer = null;
    state.noDataTimer = null;
  }

  function failRecording(message) {
    stopSensorSource();
    state.recording = false;
    state.analyzing = false;
    elements.console.classList.remove("is-recording");
    elements.liveDot.classList.remove("is-live");
    elements.liveDot.textContent = "Standby";
    elements.state.textContent = "Could not start sensor";
    elements.hint.textContent = message;
    renderError(elements.liveResult, message);
    updateControls();
  }

  function startGenericSensor() {
    const sensor = new window.Accelerometer({ frequency: 100 });
    sensor.addEventListener("reading", () => {
      appendSample(
        Number(sensor.x),
        Number(sensor.y),
        Number(sensor.z),
        elapsedSeconds(),
      );
    });
    sensor.addEventListener("error", (event) => {
      const message =
        event.error?.name === "NotAllowedError"
          ? "Motion access was denied. Allow accelerometer access in browser settings and retry."
          : "The device accelerometer could not be read. Try another supported browser or upload a CSV.";
      failRecording(message);
    });
    sensor.start();
    state.sensor = sensor;
    state.source = "High-resolution sensor";
  }

  async function startDeviceMotion() {
    if (
      typeof window.DeviceMotionEvent?.requestPermission === "function"
    ) {
      const permission = await window.DeviceMotionEvent.requestPermission();
      if (permission !== "granted") {
        throw new Error(
          "Motion access was denied. Enable Motion & Orientation Access and retry.",
        );
      }
    }
    window.addEventListener("devicemotion", handleDeviceMotion, {
      passive: true,
    });
    state.source = "Device motion sensor";
  }

  async function startRecording() {
    if (!supportsMotion || state.recording || state.analyzing) return;
    elements.liveResult.replaceChildren();
    state.samples = [];
    state.recentMagnitudes = [];
    state.lastTimestamp = 0;
    state.startedAt = performance.now();
    state.recording = true;
    elements.console.classList.add("is-recording");
    elements.state.textContent = "Requesting sensor access";
    elements.liveDot.textContent = "Live";
    elements.liveDot.classList.add("is-live");
    updateControls();

    try {
      if (
        typeof window.DeviceMotionEvent?.requestPermission === "function"
      ) {
        await startDeviceMotion();
      } else if ("Accelerometer" in window) {
        startGenericSensor();
      } else {
        await startDeviceMotion();
      }

      elements.state.textContent = "Capturing acceleration";
      elements.streamLabel.textContent = state.source;
      state.timer = window.setInterval(updateStats, 200);
      state.noDataTimer = window.setTimeout(() => {
        if (state.recording && state.samples.length === 0) {
          failRecording(
            "No motion readings arrived. Confirm sensor permission or try Safari on iPhone and Chrome on Android.",
          );
        }
      }, 5000);
    } catch (error) {
      failRecording(error.message || "Motion access could not be started.");
    }
  }

  function buildLiveCsv() {
    const parts = ["x,y,z,timestamp\n"];
    const chunkSize = 2000;
    for (let start = 0; start < state.samples.length; start += chunkSize) {
      const rows = state.samples
        .slice(start, start + chunkSize)
        .map((sample) => sample.join(","))
        .join("\n");
      parts.push(rows, "\n");
    }
    return new Blob(parts, { type: "text/csv;charset=utf-8" });
  }

  async function analyzeCsv({ file, stationary, resultElement, button }) {
    const data = new FormData();
    data.append("file", file);
    if (resultElement === elements.uploadResult) {
      const rate = document.getElementById("sample-rate").value;
      if (rate) data.append("sample_rate_hz", rate);
    }
    data.append("vehicle_stationary", String(stationary));

    renderLoading(resultElement, "Analyzing spectral windows…");
    button.disabled = true;
    try {
      const response = await fetch("/api/v1/predict/csv", {
        method: "POST",
        body: data,
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(body?.error?.message || "Analysis failed.");
      }
      renderPrediction(resultElement, body);
    } catch (error) {
      const offline = !navigator.onLine
        ? "You are offline. Reconnect to analyze this recording."
        : error.message || "The analysis service could not be reached.";
      renderError(resultElement, offline);
    } finally {
      button.disabled = false;
    }
  }

  async function stopAndAnalyze() {
    if (!state.recording) return;
    stopSensorSource();
    state.recording = false;
    state.analyzing = true;
    state.lastTimestamp = elapsedSeconds();
    elements.console.classList.remove("is-recording");
    elements.liveDot.classList.remove("is-live");
    elements.liveDot.textContent = "Analyzing";
    elements.state.textContent = "Recording complete";
    updateStats();
    updateControls();

    const rate = achievedRate();
    if (state.samples.length < MINIMUM_SAMPLES || state.lastTimestamp < 2.56) {
      state.analyzing = false;
      elements.liveDot.textContent = "Standby";
      elements.hint.textContent =
        "The recording was too short. Capture at least 30 seconds and retry.";
      renderError(
        elements.liveResult,
        "Not enough sensor data was collected for one analysis window.",
      );
      updateControls();
      return;
    }
    if (rate < MINIMUM_RATE_HZ) {
      state.analyzing = false;
      elements.liveDot.textContent = "Low rate";
      elements.hint.textContent =
        "This browser delivered data below 50 Hz. Try another browser/device or upload a higher-rate recording.";
      renderError(
        elements.liveResult,
        `The achieved ${rate.toFixed(1)} Hz rate is below the model's 50 Hz minimum.`,
      );
      updateControls();
      return;
    }

    const file = new File([buildLiveCsv()], "live-accelerometer.csv", {
      type: "text/csv",
    });
    await analyzeCsv({
      file,
      stationary: true,
      resultElement: elements.liveResult,
      button: elements.stop,
    });
    state.analyzing = false;
    elements.liveDot.textContent = "Complete";
    elements.streamLabel.textContent = `${state.samples.length.toLocaleString()} samples captured`;
    elements.hint.textContent =
      "You can record again to compare another safely stopped vehicle.";
    updateControls();
  }

  function renderLoading(target, message) {
    const card = document.createElement("div");
    card.className = "result-card result-card--loading";
    const loader = document.createElement("span");
    loader.className = "loader";
    loader.setAttribute("aria-hidden", "true");
    const text = document.createElement("span");
    text.textContent = message;
    card.append(loader, text);
    target.replaceChildren(card);
  }

  function renderError(target, message) {
    const card = document.createElement("div");
    card.className = "result-card result-card--error";
    const label = document.createElement("span");
    label.className = "result-card__label";
    label.textContent = "Needs attention";
    const title = document.createElement("h3");
    title.textContent = "Could not classify";
    const detail = document.createElement("p");
    detail.textContent = message;
    card.append(label, title, detail);
    target.replaceChildren(card);
  }

  function predictionCopy(label) {
    if (label === "NON_EV") {
      return {
        title: "Combustion signal detected",
        detail:
          "The recording contains a vibration pattern consistent with a running combustion engine.",
      };
    }
    if (label === "EV") {
      return {
        title: "No combustion signal detected",
        detail:
          "The model did not find the expected combustion-engine vibration signature. This alone does not prove the vehicle is electric.",
      };
    }
    return {
      title: "Signal is inconclusive",
      detail:
        "The available recording does not support a reliable decision. Follow the collection guidance and retry.",
    };
  }

  function renderPrediction(target, body) {
    const copy = predictionCopy(body.prediction);
    const card = document.createElement("div");
    card.className = "result-card";
    const top = document.createElement("div");
    top.className = "result-card__top";
    const copyWrap = document.createElement("div");
    const label = document.createElement("span");
    label.className = "result-card__label";
    label.textContent = `${body.decision_quality} decision quality`;
    const title = document.createElement("h3");
    title.textContent = copy.title;
    const detail = document.createElement("p");
    detail.textContent = copy.detail;
    copyWrap.append(label, title, detail);
    const confidence = document.createElement("span");
    confidence.className = "confidence-ring";
    confidence.textContent = `${Math.round(body.confidence * 100)}%`;
    confidence.setAttribute(
      "aria-label",
      `${Math.round(body.confidence * 100)} percent model confidence`,
    );
    top.append(copyWrap, confidence);
    card.append(top);

    if (body.caveats?.length) {
      const list = document.createElement("ul");
      body.caveats.forEach((caveat) => {
        const item = document.createElement("li");
        item.textContent = caveat;
        list.append(item);
      });
      card.append(list);
    }

    const meta = document.createElement("div");
    meta.className = "result-meta";
    [
      `${body.analysis.windows_selected} windows used`,
      `${body.analysis.samples_received.toLocaleString()} samples`,
      `Model ${body.model_version}`,
    ].forEach((value) => {
      const item = document.createElement("span");
      item.textContent = value;
      meta.append(item);
    });
    card.append(meta);
    target.replaceChildren(card);
  }

  function updateFileLabel() {
    const file = elements.file.files[0];
    if (!file) return;
    elements.fileDrop.classList.add("has-file");
    elements.fileName.textContent = file.name;
    elements.fileDetail.textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB · ready to analyze`;
  }

  function drawSignal() {
    const canvas = elements.canvas;
    const context = canvas.getContext("2d");
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (canvas.width !== Math.floor(width * ratio)) {
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);

    const points = state.recentMagnitudes;
    context.beginPath();
    context.strokeStyle = "rgba(25, 245, 138, 0.95)";
    context.lineWidth = 2;
    context.shadowColor = "rgba(25, 245, 138, 0.75)";
    context.shadowBlur = 12;

    if (points.length > 1) {
      const center = points.reduce((sum, point) => sum + point, 0) / points.length;
      const deviations = points.map((point) => point - center);
      const scale = Math.max(
        0.08,
        Math.max(...deviations.map((value) => Math.abs(value))),
      );
      deviations.forEach((value, index) => {
        const x = (index / Math.max(1, deviations.length - 1)) * width;
        const y = height / 2 - (value / scale) * height * 0.37;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
    } else {
      const phase = performance.now() / 520;
      for (let index = 0; index <= 90; index += 1) {
        const x = (index / 90) * width;
        const y =
          height / 2 +
          Math.sin(index * 0.52 + phase) * 2.2 +
          Math.sin(index * 0.11 + phase * 0.7) * 3.5;
        if (index === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
    }
    context.stroke();
    context.shadowBlur = 0;

    const scannerX = ((performance.now() / 22) % (width + 80)) - 40;
    const gradient = context.createLinearGradient(scannerX - 30, 0, scannerX + 30, 0);
    gradient.addColorStop(0, "rgba(25,245,138,0)");
    gradient.addColorStop(0.5, "rgba(25,245,138,0.13)");
    gradient.addColorStop(1, "rgba(25,245,138,0)");
    context.fillStyle = gradient;
    context.fillRect(scannerX - 30, 0, 60, height);
    window.requestAnimationFrame(drawSignal);
  }

  elements.safety.addEventListener("change", updateControls);
  elements.start.addEventListener("click", startRecording);
  elements.stop.addEventListener("click", stopAndAnalyze);
  elements.file.addEventListener("change", updateFileLabel);

  ["dragenter", "dragover"].forEach((name) => {
    elements.fileDrop.addEventListener(name, () =>
      elements.fileDrop.classList.add("is-dragging"),
    );
  });
  ["dragleave", "drop"].forEach((name) => {
    elements.fileDrop.addEventListener(name, () =>
      elements.fileDrop.classList.remove("is-dragging"),
    );
  });

  elements.uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = elements.file.files[0];
    if (!file) {
      renderError(elements.uploadResult, "Choose a CSV recording first.");
      return;
    }
    if (file.size > 128 * 1024 * 1024) {
      renderError(elements.uploadResult, "The CSV exceeds the 128 MB limit.");
      return;
    }
    await analyzeCsv({
      file,
      stationary: document.getElementById("stationary").checked,
      resultElement: elements.uploadResult,
      button: elements.uploadSubmit,
    });
  });

  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.installPrompt = event;
    elements.install.hidden = false;
  });

  elements.install.addEventListener("click", async () => {
    if (state.installPrompt) {
      state.installPrompt.prompt();
      await state.installPrompt.userChoice;
      state.installPrompt = null;
      elements.install.hidden = true;
      return;
    }
    setToast("On iPhone or iPad, open the Share menu and choose “Add to Home Screen.”");
  });

  window.addEventListener("appinstalled", () => {
    elements.install.hidden = true;
    setToast("EV Trace is installed and ready from your home screen.");
  });

  const isIos =
    /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  const isStandalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone;
  if (isIos && !isStandalone) {
    elements.install.hidden = false;
  }

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {
        // The detector remains usable without offline shell caching.
      });
    });
  }

  setSensorSupport();
  updateControls();
  drawSignal();
})();
