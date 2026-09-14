package com.bikemesh.ridemesh.audio

import android.content.Context
import com.konovalov.vad.silero.VadSilero
import com.konovalov.vad.silero.config.FrameSize
import com.konovalov.vad.silero.config.Mode
import com.konovalov.vad.silero.config.SampleRate
import kotlin.math.max

/** Stateful, offline Silero adapter. It converts RideMesh 20 ms PCM frames into 512-sample windows. */
internal class SileroSpeechDetector(context: Context) : AutoCloseable {
    private val chunker = PcmChunker(CHUNK_BYTES)
    private val model = VadSilero(
        context.applicationContext,
        SampleRate.SAMPLE_RATE_16K,
        FrameSize.FRAME_SIZE_512,
        Mode.NORMAL,
        speechDurationMs = 0,
        silenceDurationMs = 0,
    )
    private var lastDecision: Boolean? = null
    private var decisions = 0L
    private var totalInferenceNs = 0L
    private var maximumInferenceNs = 0L

    fun observe(pcm16: ByteArray): Boolean? {
        chunker.push(pcm16) { chunk ->
            val started = System.nanoTime()
            lastDecision = model.isSpeech(chunk)
            val elapsed = System.nanoTime() - started
            decisions++
            totalInferenceNs += elapsed
            maximumInferenceNs = max(maximumInferenceNs, elapsed)
        }
        return lastDecision
    }

    fun clearPending() {
        chunker.clear()
    }

    fun diagnostics(): String {
        val averageUs = if (decisions == 0L) 0L else totalInferenceNs / decisions / 1_000L
        return "Silero ready • decisions: $decisions • avg: ${averageUs}us • max: ${maximumInferenceNs / 1_000L}us • active: ${lastDecision == true}"
    }

    override fun close() {
        runCatching { model.close() }
    }

    companion object {
        private const val CHUNK_BYTES = 512 * 2
    }
}

/** Allocation-light sequential chunking; keeps model state aligned despite 20 ms Opus frames. */
internal class PcmChunker(private val chunkBytes: Int) {
    private val pending = ByteArray(chunkBytes)
    private var size = 0

    init { require(chunkBytes > 0) }

    fun push(bytes: ByteArray, onChunk: (ByteArray) -> Unit) {
        var offset = 0
        while (offset < bytes.size) {
            val copied = minOf(chunkBytes - size, bytes.size - offset)
            bytes.copyInto(pending, size, offset, offset + copied)
            size += copied
            offset += copied
            if (size == chunkBytes) {
                val complete = pending.copyOf()
                size = 0
                onChunk(complete)
            }
        }
    }

    fun clear() { size = 0 }
}
