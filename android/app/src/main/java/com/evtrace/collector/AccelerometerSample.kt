package com.evtrace.collector

data class AccelerometerSample(
    val x: Float,
    val y: Float,
    val z: Float,
    val timestampSeconds: Double,
)
