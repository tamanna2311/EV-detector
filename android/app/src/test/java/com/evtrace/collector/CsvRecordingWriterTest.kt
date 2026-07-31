package com.evtrace.collector

import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class CsvRecordingWriterTest {
    @get:Rule
    val temporaryFolder = TemporaryFolder()

    @Test
    fun writesBackendCompatibleCsv() {
        val destination = temporaryFolder.newFile("recording.csv")
        CsvRecordingWriter.write(
            destination,
            listOf(
                AccelerometerSample(1.25f, -0.5f, 9.81f, 0.0),
                AccelerometerSample(1.5f, -0.25f, 9.82f, 0.005),
            ),
        )

        assertEquals(
            listOf(
                "x,y,z,timestamp",
                "1.25,-0.5,9.81,0.0",
                "1.5,-0.25,9.82,0.005",
            ),
            destination.readLines(),
        )
    }
}
