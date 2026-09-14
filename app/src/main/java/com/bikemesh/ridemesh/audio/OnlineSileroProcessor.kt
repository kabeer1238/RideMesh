package com.bikemesh.ridemesh.audio

import android.content.Context
import android.media.AudioFormat
import java.nio.ByteBuffer
import java.util.ArrayDeque
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import java.util.concurrent.atomic.AtomicReference

/**
 * Opt-in WebRTC capture gate, not a replacement transport or audio device.
 * Inference runs on a bounded worker, NEVER on WebRTC's capture thread.
 * Only microphone PCM enters this object. No playback/system audio is captured.
 * Model/format/worker failure bypasses VAD; mute/interruption still always zeros PCM.
 */
internal class OnlineSileroProcessor(context: Context) : AutoCloseable {
    private data class Frame(val epoch: Long, val end: Long, val pcm: ByteArray,
                             val rate: Int, val timestamp: Long)
    private data class Decision(val epoch: Long, val processed: Long, val speechThrough: Long)
    private val appContext = context.applicationContext
    private val queue = ArrayBlockingQueue<Frame>(20)
    private val epoch = AtomicLong(0)
    private val decision = AtomicReference(Decision(-1, 0, -1))
    private val delayed = ArrayDeque<Frame>() // capture-thread owned
    @Volatile private var allowed = false
    @Volatile private var closed = false
    @Volatile private var ready = false
    @Volatile private var failure: String? = null
    @Volatile private var modelStats = "starting"
    @Volatile private var passed = 0L
    @Volatile private var suppressed = 0L
    @Volatile private var late = 0L
    private var captureEpoch = -1L
    private var captureRate = 0
    private var endSample = 0L
    private var consecutiveLate = 0
    private var gain = 1.0

    private val worker = Thread({ inferLoop() }, "RideMesh-Online-Silero").apply {
        isDaemon = true
        start()
    }

    fun setAllowed(value: Boolean) {
        if (allowed != value) {
            allowed = value
            epoch.incrementAndGet() // invalidates all buffered audio and in-flight results
            queue.clear()
        }
    }

    fun bypass() { failure = "disabled in Settings; normal WebRTC"; queue.clear() }

    fun diagnostics(): String =
        "Online Silero: " + (failure?.let { "BYPASS ($it)" }
            ?: if (!ready) "STARTING / normal WebRTC" else if (!allowed) "PAUSED" else "ON") +
            " • lookahead: 100 ms • passed: $passed • gated: $suppressed • late: $late • $modelStats"

    private fun inferLoop() {
        var detector: SileroSpeechDetector? = null
        var workerEpoch = epoch.get()
        var speechThrough = -1L
        try {
            detector = SileroSpeechDetector(appContext)
            ready = true
            while (!closed && failure == null) {
                val frame = queue.poll(100, TimeUnit.MILLISECONDS) ?: continue
                if (frame.epoch != epoch.get() || !allowed) continue
                if (workerEpoch != frame.epoch) {
                    detector.close()
                    detector = SileroSpeechDetector(appContext) // reset recurrent state too
                    workerEpoch = frame.epoch
                    speechThrough = -1L
                }
                val speech = detector.observe(OnlineVadPolicy.analysisFrame(frame.pcm, frame.rate))
                if (speech == true) speechThrough = frame.end + OnlineVadPolicy.HANGOVER_SAMPLES
                if (frame.epoch == epoch.get() && allowed && !closed) {
                    decision.set(Decision(frame.epoch, frame.end, speechThrough))
                }
                if (frame.end % 16_000L == 0L) modelStats = detector.diagnostics()
            }
        } catch (_: InterruptedException) {
            if (!closed) failure = "worker interrupted"
        } catch (_: Throwable) {
            failure = "model unavailable"
        } finally {
            ready = false
            detector?.close()
            queue.clear()
        }
    }

    /** Called only by the ADM. Returns the capture timestamp matching the buffered PCM. */
    fun process(buffer: ByteBuffer, format: Int, channels: Int, rate: Int,
                bytesRead: Int, timestamp: Long): Long {
        val token = epoch.get()
        try {
            if (captureEpoch != token || captureRate != rate) {
                if (captureRate != 0 && captureRate != rate) {
                    captureRate = rate
                    epoch.incrementAndGet()
                    return silence(buffer, timestamp)
                }
                captureEpoch = token
                captureRate = rate
                delayed.clear()
                queue.clear()
                endSample = 0
                consecutiveLate = 0
                gain = 1.0
            }
            if (!allowed || closed) {
                delayed.clear()
                return silence(buffer, timestamp)
            }
            if (!ready || failure != null) return timestamp
            if (format != AudioFormat.ENCODING_PCM_16BIT || channels != 1 ||
                rate !in intArrayOf(8_000, 16_000, 32_000, 48_000) ||
                bytesRead != rate / 100 * 2 || buffer.capacity() != bytesRead) {
                failure = "unsupported capture format; normal WebRTC"
                delayed.clear()
                queue.clear()
                return timestamp
            }

            val pcm = ByteArray(bytesRead)
            buffer.duplicate().apply { clear(); get(pcm) }
            endSample += 160
            val frame = Frame(token, endSample, pcm, rate, timestamp)
            if (!queue.offer(frame)) {
                failure = "analysis queue full; normal WebRTC"
                delayed.clear()
                queue.clear()
                return timestamp
            }
            delayed.addLast(frame)
            if (delayed.size <= OnlineVadPolicy.LOOKAHEAD_FRAMES) {
                return silence(buffer, if (timestamp > 100_000_000L) timestamp - 100_000_000L else 0L)
            }
            val queuedOutput = delayed.removeFirst()
            val output = queuedOutput.copy(pcm = queuedOutput.pcm.copyOf())
            val state = decision.get()
            val processed = if (state.epoch == token) state.processed else 0L
            if (processed < output.end + OnlineVadPolicy.DECISION_LOOKAHEAD) {
                late++
                consecutiveLate++
            } else consecutiveLate = 0
            if (consecutiveLate >= 3) {
                failure = "analysis too slow; normal WebRTC"
                delayed.clear()
                queue.clear()
                return timestamp
            }
            val pass = OnlineVadPolicy.pass(output.end, processed,
                if (state.epoch == token) state.speechThrough else -1L)
            if (pass) passed++ else suppressed++
            val target = if (pass) 1.0 else 0.0
            // 8 ms ramp avoids a click at gate boundaries; original PCM otherwise unchanged.
            val step = 1.0 / (rate * 0.008)
            for (i in output.pcm.indices step 2) {
                gain = if (gain < target) minOf(target, gain + step) else maxOf(target, gain - step)
                val sample = ((output.pcm[i].toInt() and 255) or
                    (output.pcm[i + 1].toInt() shl 8)).toShort().toInt()
                val scaled = (sample * gain).toInt()
                output.pcm[i] = scaled.toByte()
                output.pcm[i + 1] = (scaled shr 8).toByte()
            }
            // No buffered audio survives a mute/call transition occurring during this callback.
            if (!allowed || closed || epoch.get() != token) return silence(buffer, timestamp)
            buffer.duplicate().apply { clear(); put(output.pcm) }
            return output.timestamp
        } catch (_: Throwable) {
            failure = "capture processing failed; normal WebRTC"
            delayed.clear()
            queue.clear()
            return if (!allowed || closed || epoch.get() != token) silence(buffer, timestamp) else timestamp
        } finally {
            if (!allowed || closed || epoch.get() != token) silence(buffer, timestamp)
        }
    }

    private fun silence(buffer: ByteBuffer, timestamp: Long): Long {
        for (i in 0 until buffer.capacity()) buffer.put(i, 0.toByte())
        return timestamp
    }

    override fun close() {
        allowed = false
        closed = true
        epoch.incrementAndGet()
        queue.clear()
        worker.interrupt() // model closes on its owning thread; never wait on the capture thread
    }
}
