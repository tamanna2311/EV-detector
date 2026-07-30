package com.evtrace.collector

import org.junit.Assert.assertEquals
import org.junit.Test

class RateCalculatorTest {
    @Test
    fun calculatesTwoHundredHertzFromSensorTimestamps() {
        val samples =
            (0..6_000).map { index ->
                AccelerometerSample(
                    x = 0f,
                    y = 0f,
                    z = 9.81f,
                    timestampSeconds = index * 0.005,
                )
            }

        val stats = RateCalculator.from(samples)

        assertEquals(6_001, stats.sampleCount)
        assertEquals(30.0, stats.durationSeconds, 1e-9)
        assertEquals(200.0, stats.achievedRateHz, 1e-9)
    }

    @Test
    fun handlesInsufficientSamples() {
        val stats =
            RateCalculator.from(
                listOf(AccelerometerSample(0f, 0f, 9.81f, 0.0)),
            )

        assertEquals(1, stats.sampleCount)
        assertEquals(0.0, stats.achievedRateHz, 0.0)
    }
}
