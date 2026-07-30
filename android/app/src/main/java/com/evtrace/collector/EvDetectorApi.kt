package com.evtrace.collector

import org.json.JSONObject
import java.io.BufferedOutputStream
import java.io.DataOutputStream
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID

class EvDetectorApi(
    private val baseUrl: String,
) {
    fun predict(csvFile: File): PredictionResult {
        val boundary = "----EVTrace${UUID.randomUUID()}"
        val connection =
            (URL("$baseUrl/api/v1/predict/csv").openConnection() as HttpURLConnection)
                .apply {
                    requestMethod = "POST"
                    connectTimeout = 30_000
                    readTimeout = 180_000
                    doOutput = true
                    useCaches = false
                    setRequestProperty(
                        "Content-Type",
                        "multipart/form-data; boundary=$boundary",
                    )
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("X-Request-ID", UUID.randomUUID().toString())
                }

        try {
            DataOutputStream(BufferedOutputStream(connection.outputStream)).use { output ->
                writeFormField(output, boundary, "vehicle_stationary", "true")
                writeFileField(output, boundary, csvFile)
                output.writeBytes("--$boundary--\r\n")
                output.flush()
            }

            val responseCode = connection.responseCode
            val responseStream =
                if (responseCode in 200..299) connection.inputStream
                else connection.errorStream
            val responseBody =
                responseStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }
                    ?: ""

            if (responseCode !in 200..299) {
                val message =
                    runCatching {
                        JSONObject(responseBody)
                            .getJSONObject("error")
                            .getString("message")
                    }.getOrDefault("Prediction failed with HTTP $responseCode.")
                throw ApiException(message)
            }
            return parsePrediction(responseBody)
        } finally {
            connection.disconnect()
        }
    }

    internal fun parsePrediction(responseBody: String): PredictionResult {
        val body = JSONObject(responseBody)
        val caveatsJson = body.optJSONArray("caveats")
        val caveats = buildList {
            if (caveatsJson != null) {
                for (index in 0 until caveatsJson.length()) {
                    add(caveatsJson.getString(index))
                }
            }
        }
        val analysis = body.getJSONObject("analysis")
        return PredictionResult(
            prediction = body.getString("prediction"),
            confidence = body.getDouble("confidence"),
            quality = body.getString("decision_quality"),
            caveats = caveats,
            windowsSelected = analysis.getInt("windows_selected"),
            samplesReceived = analysis.getInt("samples_received"),
            modelVersion = body.getString("model_version"),
        )
    }

    private fun writeFormField(
        output: DataOutputStream,
        boundary: String,
        name: String,
        value: String,
    ) {
        output.writeBytes("--$boundary\r\n")
        output.writeBytes("Content-Disposition: form-data; name=\"$name\"\r\n\r\n")
        output.writeBytes(value)
        output.writeBytes("\r\n")
    }

    private fun writeFileField(
        output: DataOutputStream,
        boundary: String,
        csvFile: File,
    ) {
        output.writeBytes("--$boundary\r\n")
        output.writeBytes(
            "Content-Disposition: form-data; name=\"file\"; " +
                "filename=\"${csvFile.name}\"\r\n",
        )
        output.writeBytes("Content-Type: text/csv\r\n\r\n")
        csvFile.inputStream().buffered().use { input -> input.copyTo(output) }
        output.writeBytes("\r\n")
    }
}

class ApiException(message: String) : Exception(message)
