package com.evtrace.collector

import java.io.File

object CsvRecordingWriter {
    fun write(destination: File, samples: List<AccelerometerSample>): File {
        destination.bufferedWriter(Charsets.UTF_8).use { writer ->
            writer.appendLine("x,y,z,timestamp")
            for (sample in samples) {
                writer.append(sample.x.toString())
                writer.append(',')
                writer.append(sample.y.toString())
                writer.append(',')
                writer.append(sample.z.toString())
                writer.append(',')
                writer.appendLine(sample.timestampSeconds.toString())
            }
        }
        return destination
    }
}
