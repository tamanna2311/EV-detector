package com.evtrace.collector

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.SpannableString
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.CheckBox
import android.widget.ProgressBar
import android.widget.TextView
import java.io.File
import java.util.Locale
import java.util.concurrent.Executors
import kotlin.math.floor

class MainActivity : Activity() {
    companion object {
        private const val RECOMMENDED_SECONDS = 30
        private const val MINIMUM_SECONDS = 2.56
        private const val MINIMUM_SAMPLES = 128
        private const val MINIMUM_RATE_HZ = 50.0
    }

    private lateinit var collector: AccelerometerCollector
    private val mainHandler = Handler(Looper.getMainLooper())
    private val networkExecutor = Executors.newSingleThreadExecutor()
    private val api by lazy { EvDetectorApi(BuildConfig.API_BASE_URL) }

    private lateinit var safetyConfirmation: CheckBox
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var sensorDescription: TextView
    private lateinit var recordingState: TextView
    private lateinit var durationValue: TextView
    private lateinit var sampleValue: TextView
    private lateinit var rateValue: TextView
    private lateinit var guidance: TextView
    private lateinit var progress: ProgressBar
    private lateinit var resultCard: View
    private lateinit var resultQuality: TextView
    private lateinit var resultTitle: TextView
    private lateinit var resultDetail: TextView
    private lateinit var resultConfidence: TextView
    private lateinit var resultCaveats: TextView
    private lateinit var resultMeta: TextView

    private var recording = false
    private var analyzing = false

    private val statsTicker =
        object : Runnable {
            override fun run() {
                if (!recording) return
                val stats = collector.stats()
                renderStats(stats)
                guidance.text =
                    when {
                        stats.limitReached ->
                            getString(R.string.sample_limit_reached)
                        stats.durationSeconds >= RECOMMENDED_SECONDS ->
                            getString(R.string.recommended_duration_reached)
                        else -> {
                            val remaining =
                                (RECOMMENDED_SECONDS - stats.durationSeconds)
                                    .toInt()
                                    .coerceAtLeast(1)
                            resources.getQuantityString(
                                R.plurals.seconds_remaining,
                                remaining,
                                remaining,
                            )
                        }
                    }
                mainHandler.postDelayed(this, 200)
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        bindViews()

        val title = SpannableString(getString(R.string.hero_title))
        title.setSpan(
            ForegroundColorSpan(Color.parseColor("#19F58A")),
            0,
            6,
            Spanned.SPAN_EXCLUSIVE_EXCLUSIVE,
        )
        findViewById<TextView>(R.id.hero_title).text = title

        collector = AccelerometerCollector(this)
        sensorDescription.text = collector.sensorSummary
        if (!collector.isAvailable) {
            recordingState.text = getString(R.string.accelerometer_unavailable)
        }

        safetyConfirmation.setOnCheckedChangeListener { _, _ -> updateControls() }
        startButton.setOnClickListener { startRecording() }
        stopButton.setOnClickListener { stopAndAnalyze() }
        updateControls()
    }

    private fun bindViews() {
        safetyConfirmation = findViewById(R.id.safety_confirmation)
        startButton = findViewById(R.id.start_recording)
        stopButton = findViewById(R.id.stop_recording)
        sensorDescription = findViewById(R.id.sensor_description)
        recordingState = findViewById(R.id.recording_state)
        durationValue = findViewById(R.id.duration_value)
        sampleValue = findViewById(R.id.sample_value)
        rateValue = findViewById(R.id.rate_value)
        guidance = findViewById(R.id.guidance)
        progress = findViewById(R.id.duration_progress)
        resultCard = findViewById(R.id.result_card)
        resultQuality = findViewById(R.id.result_quality)
        resultTitle = findViewById(R.id.result_title)
        resultDetail = findViewById(R.id.result_detail)
        resultConfidence = findViewById(R.id.result_confidence)
        resultCaveats = findViewById(R.id.result_caveats)
        resultMeta = findViewById(R.id.result_meta)
    }

    private fun startRecording() {
        if (!safetyConfirmation.isChecked || recording || analyzing) return
        resultCard.visibility = View.GONE
        if (!collector.start()) {
            showError(getString(R.string.accelerometer_start_failed))
            return
        }

        recording = true
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        recordingState.text = getString(R.string.capturing_acceleration)
        guidance.text = getString(R.string.recording_guidance)
        renderStats(RecordingStats(0, 0.0, 0.0, false))
        mainHandler.removeCallbacks(statsTicker)
        mainHandler.post(statsTicker)
        updateControls()
    }

    private fun stopAndAnalyze() {
        if (!recording) return
        recording = false
        mainHandler.removeCallbacks(statsTicker)
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val samples = collector.stop()
        val stats = RateCalculator.from(samples)
        renderStats(stats)
        recordingState.text = getString(R.string.recording_complete)

        when {
            samples.size < MINIMUM_SAMPLES || stats.durationSeconds < MINIMUM_SECONDS -> {
                showError(getString(R.string.minimum_recording_error))
                updateControls()
                return
            }
            stats.achievedRateHz < MINIMUM_RATE_HZ -> {
                showError(
                    getString(R.string.minimum_rate_error, stats.achievedRateHz),
                )
                updateControls()
                return
            }
        }

        analyzing = true
        recordingState.text = getString(R.string.analyzing_signal)
        guidance.text = getString(R.string.uploading_securely)
        updateControls()
        resultCard.visibility = View.VISIBLE
        resultQuality.text = getString(R.string.analysis_in_progress)
        resultTitle.text = getString(R.string.reading_spectrum)
        resultDetail.text = getString(R.string.analysis_wait)
        resultConfidence.text = getString(R.string.working_indicator)
        resultCaveats.text = ""
        resultMeta.text = ""

        networkExecutor.execute {
            runCatching {
                val file =
                    CsvRecordingWriter.write(
                        File(cacheDir, "ev-trace-${System.currentTimeMillis()}.csv"),
                        samples,
                    )
                try {
                    api.predict(file)
                } finally {
                    file.delete()
                }
            }.onSuccess { result ->
                runOnUiThread {
                    analyzing = false
                    renderPrediction(result)
                    recordingState.text = getString(R.string.analysis_complete)
                    guidance.text = getString(R.string.ready_to_compare)
                    updateControls()
                }
            }.onFailure { error ->
                runOnUiThread {
                    analyzing = false
                    showError(error.message ?: getString(R.string.analysis_service_error))
                    recordingState.text = getString(R.string.analysis_failed)
                    updateControls()
                }
            }
        }
    }

    private fun renderStats(stats: RecordingStats) {
        durationValue.text = formatDuration(stats.durationSeconds)
        sampleValue.text = "%,d".format(Locale.US, stats.sampleCount)
        rateValue.text =
            if (stats.achievedRateHz > 0) {
                "%.1f Hz".format(Locale.US, stats.achievedRateHz)
            } else {
                getString(R.string.rate_unavailable)
            }
        progress.progress =
            ((stats.durationSeconds / RECOMMENDED_SECONDS) * 100)
                .toInt()
                .coerceIn(0, 100)
    }

    private fun renderPrediction(result: PredictionResult) {
        val copy =
            when (result.prediction) {
                "NON_EV" ->
                    getString(R.string.non_ev_title) to getString(R.string.non_ev_detail)
                "EV" ->
                    getString(R.string.ev_title) to getString(R.string.ev_detail)
                else ->
                    getString(R.string.inconclusive_title) to
                        getString(R.string.inconclusive_detail)
            }
        resultCard.visibility = View.VISIBLE
        resultQuality.text = getString(R.string.decision_quality, result.quality)
        resultTitle.text = copy.first
        resultDetail.text = copy.second
        resultConfidence.text =
            getString(R.string.confidence_percent, (result.confidence * 100).toInt())
        resultCaveats.text =
            if (result.caveats.isEmpty()) ""
            else result.caveats.joinToString(separator = "\n") { "• $it" }
        resultMeta.text =
            getString(
                R.string.result_metadata,
                resources.getQuantityString(
                    R.plurals.windows_count,
                    result.windowsSelected,
                    result.windowsSelected,
                ),
                resources.getQuantityString(
                    R.plurals.samples_count,
                    result.samplesReceived,
                    result.samplesReceived,
                ),
                result.modelVersion,
            )
    }

    private fun showError(message: String) {
        resultCard.visibility = View.VISIBLE
        resultQuality.text = getString(R.string.needs_attention)
        resultTitle.text = getString(R.string.could_not_classify)
        resultDetail.text = message
        resultConfidence.text = getString(R.string.error_mark)
        resultCaveats.text = ""
        resultMeta.text = ""
        guidance.text = message
    }

    private fun updateControls() {
        startButton.isEnabled =
            collector.isAvailable &&
            safetyConfirmation.isChecked &&
            !recording &&
            !analyzing
        stopButton.isEnabled = recording && !analyzing
        safetyConfirmation.isEnabled = !recording && !analyzing
    }

    private fun formatDuration(seconds: Double): String {
        val total = floor(seconds.coerceAtLeast(0.0)).toInt()
        return "%02d:%02d".format(Locale.US, total / 60, total % 60)
    }

    override fun onStop() {
        if (recording) {
            recording = false
            collector.stop()
            mainHandler.removeCallbacks(statsTicker)
            window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            recordingState.text = getString(R.string.recording_cancelled)
            guidance.text = getString(R.string.foreground_required)
            updateControls()
        }
        super.onStop()
    }

    override fun onDestroy() {
        mainHandler.removeCallbacksAndMessages(null)
        networkExecutor.shutdownNow()
        collector.close()
        super.onDestroy()
    }
}
