package com.evtrace.collector

data class PredictionResult(
    val prediction: String,
    val confidence: Double,
    val quality: String,
    val caveats: List<String>,
    val windowsSelected: Int,
    val samplesReceived: Int,
    val modelVersion: String,
)
