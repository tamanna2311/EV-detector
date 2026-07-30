package com.evtrace.collector

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Handler
import android.os.HandlerThread
import java.io.Closeable

class AccelerometerCollector(context: Context) : SensorEventListener, Closeable {
    companion object {
        const val REQUESTED_PERIOD_US = 5_000
        const val REQUESTED_RATE_HZ = 200
        const val MAX_SAMPLES = 100_000
    }

    private val sensorManager =
        context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    private val accelerometer =
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val sensorThread =
        HandlerThread("ev-trace-accelerometer").apply { start() }
    private val sensorHandler = Handler(sensorThread.looper)
    private val lock = Any()
    private val samples = ArrayList<AccelerometerSample>(12_000)

    @Volatile
    private var recording = false
    private var firstTimestampNs: Long? = null
    private var limitReached = false

    val isAvailable: Boolean
        get() = accelerometer != null

    val sensorSummary: String
        get() {
            val sensor = accelerometer ?: return "Accelerometer unavailable"
            val maximumRate =
                if (sensor.minDelay > 0) 1_000_000.0 / sensor.minDelay else 0.0
            val rateText =
                if (maximumRate > 0) "up to %.0f Hz advertised".format(maximumRate)
                else "maximum rate not reported"
            return "${sensor.name} · $rateText"
        }

    fun start(): Boolean {
        val sensor = accelerometer ?: return false
        sensorManager.unregisterListener(this)
        synchronized(lock) {
            samples.clear()
            firstTimestampNs = null
            limitReached = false
            recording = true
        }

        val registered =
            sensorManager.registerListener(
                this,
                sensor,
                REQUESTED_PERIOD_US,
                0,
                sensorHandler,
            )
        if (!registered) {
            recording = false
        }
        return registered
    }

    fun stop(): List<AccelerometerSample> {
        recording = false
        sensorManager.unregisterListener(this)
        synchronized(lock) {
            return samples.toList()
        }
    }

    fun stats(): RecordingStats {
        synchronized(lock) {
            if (samples.size < 2) {
                return RecordingStats(
                    sampleCount = samples.size,
                    durationSeconds = 0.0,
                    achievedRateHz = 0.0,
                    limitReached = limitReached,
                )
            }
            val duration =
                samples.last().timestampSeconds - samples.first().timestampSeconds
            val rate = if (duration > 0) (samples.size - 1) / duration else 0.0
            return RecordingStats(
                sampleCount = samples.size,
                durationSeconds = duration,
                achievedRateHz = rate,
                limitReached = limitReached,
            )
        }
    }

    override fun onSensorChanged(event: SensorEvent) {
        if (!recording || event.sensor.type != Sensor.TYPE_ACCELEROMETER) {
            return
        }

        synchronized(lock) {
            if (!recording) return
            if (samples.size >= MAX_SAMPLES) {
                limitReached = true
                return
            }
            val start = firstTimestampNs ?: event.timestamp.also { firstTimestampNs = it }
            val timestampSeconds = (event.timestamp - start) / 1_000_000_000.0
            samples.add(
                AccelerometerSample(
                    x = event.values[0],
                    y = event.values[1],
                    z = event.values[2],
                    timestampSeconds = timestampSeconds,
                ),
            )
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    override fun close() {
        recording = false
        sensorManager.unregisterListener(this)
        sensorThread.quitSafely()
    }
}
