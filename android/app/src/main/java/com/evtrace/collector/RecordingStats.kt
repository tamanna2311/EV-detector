package com.evtrace.collector

data class RecordingStats(
    val sampleCount: Int,
    val durationSeconds: Double,
    val achievedRateHz: Double,
    val limitReached: Boolean,
)

object RateCalculator {
    fun from(samples: List<AccelerometerSample>): RecordingStats {
        if (samples.size < 2) {
            return RecordingStats(
                sampleCount = samples.size,
                durationSeconds = 0.0,
                achievedRateHz = 0.0,
                limitReached = false,
            )
        }

        val duration =
            samples.last().timestampSeconds - samples.first().timestampSeconds
        val rate = if (duration > 0.0) (samples.size - 1) / duration else 0.0
        return RecordingStats(
            sampleCount = samples.size,
            durationSeconds = duration,
            achievedRateHz = rate,
            limitReached = false,
        )
    }
}
