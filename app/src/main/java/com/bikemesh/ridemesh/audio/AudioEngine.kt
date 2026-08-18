package com.bikemesh.ridemesh.audio

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.PI
import kotlin.math.max
import kotlin.math.sqrt

enum class AudioRoute {
    AUTO,
    PHONE,
    HELMET,
}

class AudioEngine(
    context: Context,
    private val onCapturedFrame: (ByteArray) -> Unit,
    private val onStatus: (String) -> Unit,
) {
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val capturing = AtomicBoolean(false)
    private val playbackRunning = AtomicBoolean(true)

    /**
     * Incoming audio is kept per remote rider and mixed into one 20 ms output frame.
     * This prevents a three-rider call from serialising two remote 20 ms frames into
     * 40 ms of playback every 20 ms, which was the main source of growing delay/jitter.
     */
    private val sourceQueues = ConcurrentHashMap<String, ArrayDeque<ByteArray>>()
    private val sourcePrimed = ConcurrentHashMap.newKeySet<String>()
    private val sourceLastSeenMs = ConcurrentHashMap<String, Long>()

    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var audioTrack: AudioTrack? = null
    @Volatile private var route: AudioRoute = AudioRoute.AUTO
    @Volatile private var playbackActiveUntilMs = 0L

    private val playbackThread = Thread({ playbackLoop() }, "RideMesh-Mixer").apply {
        isDaemon = true
        start()
    }

    fun setRoute(newRoute: AudioRoute) {
        route = newRoute
    }

    @SuppressLint("MissingPermission")
    fun selectCommunicationDevice(): String {
        return try {
            audioManager.mode = AudioManager.MODE_IN_COMMUNICATION

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val available = audioManager.availableCommunicationDevices
                val helmet = available.firstOrNull { it.isHelmetCandidate() }
                val speaker = available.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }

                val chosen = when (route) {
                    AudioRoute.HELMET -> helmet
                    AudioRoute.PHONE -> speaker
                    AudioRoute.AUTO -> helmet ?: speaker
                }

                if (chosen == null) {
                    val text = when (route) {
                        AudioRoute.HELMET -> "Audio: no call-capable Bluetooth headset found"
                        AudioRoute.PHONE -> "Audio: phone speaker unavailable"
                        AudioRoute.AUTO -> "Audio: no communication device available"
                    }
                    onStatus(text)
                    text
                } else {
                    val ok = audioManager.setCommunicationDevice(chosen)
                    val label = chosen.routeLabel()
                    val text = if (ok) "Audio: $label" else "Audio routing failed: $label"
                    onStatus(text)
                    text
                }
            } else {
                val hasBluetoothSco = audioManager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                    .any { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO }

                val useBluetooth = when (route) {
                    AudioRoute.HELMET -> true
                    AudioRoute.PHONE -> false
                    AudioRoute.AUTO -> hasBluetoothSco
                }

                @Suppress("DEPRECATION")
                if (useBluetooth) {
                    audioManager.isSpeakerphoneOn = false
                    audioManager.startBluetoothSco()
                    audioManager.isBluetoothScoOn = true
                    "Audio: Bluetooth headset"
                } else {
                    audioManager.stopBluetoothSco()
                    audioManager.isBluetoothScoOn = false
                    audioManager.isSpeakerphoneOn = true
                    "Audio: phone speaker + microphone"
                }.also(onStatus)
            }
        } catch (t: Throwable) {
            val text = "Audio routing error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"
            onStatus(text)
            text
        }
    }

    @SuppressLint("MissingPermission")
    fun startTransmit() {
        if (!capturing.compareAndSet(false, true)) return

        var recorder: AudioRecord? = null
        try {
            selectCommunicationDevice()

            val min = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_IN, ENCODING)
            if (min <= 0) {
                capturing.set(false)
                onStatus("Microphone buffer unavailable")
                return
            }
            val recordBuffer = max(min, FRAME_BYTES * 4)

            recorder = AudioRecord(
                MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                SAMPLE_RATE,
                CHANNEL_IN,
                ENCODING,
                recordBuffer,
            )

            if (recorder.state != AudioRecord.STATE_INITIALIZED) {
                capturing.set(false)
                recorder.release()
                onStatus("Microphone could not start")
                return
            }

            val aec = createAec(recorder.audioSessionId)
            val ns = createNs(recorder.audioSessionId)
            val agc = createAgc(recorder.audioSessionId)

            audioRecord = recorder
            recorder.startRecording()
            onStatus("HANDS-FREE • ECHO GUARD • VAD • ${effectsLabel(aec != null, ns != null, agc != null)}")

            val activeRecorder = recorder
            Thread({
                val frame = ByteArray(FRAME_BYTES)
                val preRoll = ArrayDeque<ByteArray>(VAD_PREROLL_FRAMES)
                val windFilter = WindRumbleFilter(SAMPLE_RATE, WIND_FILTER_CUTOFF_HZ)
                var hangover = 0
                var wasSending = false
                var noiseFloor = VAD_INITIAL_NOISE_FLOOR

                try {
                    while (capturing.get()) {
                        val read = activeRecorder.read(frame, 0, frame.size)
                        if (read <= 0) continue

                        val raw = if (read == frame.size) frame.copyOf() else frame.copyOf(read)
                        val current = windFilter.process(raw)
                        val rms = pcmRms(current)

                        val normalThreshold = max(VAD_MIN_RMS, noiseFloor * VAD_NOISE_MULTIPLIER)
                        val farEndAudioActive = System.currentTimeMillis() < playbackActiveUntilMs
                        val echoThreshold = if (aec != null) {
                            max(VAD_ECHO_MIN_RMS_AEC, normalThreshold * VAD_ECHO_MULTIPLIER_AEC)
                        } else {
                            max(VAD_ECHO_MIN_RMS_NO_AEC, normalThreshold * VAD_ECHO_MULTIPLIER_NO_AEC)
                        }
                        val speechThreshold = if (farEndAudioActive) echoThreshold else normalThreshold
                        val speech = rms >= speechThreshold

                        // Do not learn loud far-end playback as the new road-noise floor.
                        if (!speech && !farEndAudioActive) {
                            noiseFloor = (noiseFloor * 0.985) + (rms * 0.015)
                        }

                        if (speech) hangover = VAD_HANGOVER_FRAMES
                        else if (hangover > 0) hangover--

                        val sending = speech || hangover > 0
                        if (sending) {
                            if (!wasSending) {
                                while (preRoll.isNotEmpty()) onCapturedFrame(preRoll.removeFirst())
                            }
                            onCapturedFrame(current)
                        } else {
                            if (preRoll.size >= VAD_PREROLL_FRAMES) preRoll.removeFirst()
                            preRoll.addLast(current)
                        }
                        wasSending = sending
                    }
                } catch (t: Throwable) {
                    onStatus("Microphone stream error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")
                } finally {
                    try { activeRecorder.stop() } catch (_: Throwable) {}
                    aec?.release()
                    ns?.release()
                    agc?.release()
                    activeRecorder.release()
                    if (audioRecord === activeRecorder) audioRecord = null
                    selectCommunicationDevice()
                }
            }, "RideMesh-Mic").start()
        } catch (t: Throwable) {
            capturing.set(false)
            try { recorder?.release() } catch (_: Throwable) {}
            if (audioRecord === recorder) audioRecord = null
            onStatus("Microphone error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")
        }
    }

    fun stopTransmit() {
        capturing.set(false)
    }

    /**
     * Queue one remote rider independently. Each source is capped at ~60 ms so a weak
     * network cannot create seconds of old speech. Two frames are collected before a
     * source starts, giving a small jitter buffer without noticeable conversational lag.
     */
    fun playIncoming(sourceId: String, audio: ByteArray) {
        if (audio.isEmpty() || !playbackRunning.get()) return
        val key = sourceId.ifBlank { "unknown" }
        val normalized = when {
            audio.size == FRAME_BYTES -> audio.copyOf()
            audio.size > FRAME_BYTES -> audio.copyOf(FRAME_BYTES)
            else -> audio.copyOf(FRAME_BYTES)
        }
        val queue = sourceQueues.computeIfAbsent(key) { ArrayDeque(SOURCE_QUEUE_MAX_FRAMES) }
        synchronized(queue) {
            while (queue.size >= SOURCE_QUEUE_MAX_FRAMES) queue.removeFirst()
            queue.addLast(normalized)
            if (queue.size >= SOURCE_PRIME_FRAMES) sourcePrimed.add(key)
        }
        sourceLastSeenMs[key] = System.currentTimeMillis()
    }

    private fun playbackLoop() {
        while (playbackRunning.get()) {
            try {
                val frames = ArrayList<ByteArray>(sourceQueues.size)
                val now = System.currentTimeMillis()

                for ((sourceId, queue) in sourceQueues) {
                    val frame = synchronized(queue) {
                        if (!sourcePrimed.contains(sourceId) && queue.size >= SOURCE_PRIME_FRAMES) {
                            sourcePrimed.add(sourceId)
                        }
                        if (sourcePrimed.contains(sourceId) && queue.isNotEmpty()) queue.removeFirst() else null
                    }
                    if (frame != null) frames.add(frame)

                    val lastSeen = sourceLastSeenMs[sourceId] ?: now
                    if (now - lastSeen > SOURCE_EXPIRE_MS && synchronized(queue) { queue.isEmpty() }) {
                        sourceQueues.remove(sourceId, queue)
                        sourcePrimed.remove(sourceId)
                        sourceLastSeenMs.remove(sourceId)
                    }
                }

                if (frames.isEmpty()) {
                    Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                    continue
                }

                val mixed = mixFrames(frames)
                val track = ensureTrack()
                if (track == null) {
                    Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                    continue
                }

                playbackActiveUntilMs = System.currentTimeMillis() + ECHO_GUARD_AFTER_PLAYBACK_MS
                track.write(mixed, 0, mixed.size, AudioTrack.WRITE_BLOCKING)
            } catch (_: InterruptedException) {
                break
            } catch (_: Throwable) {
                Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
            }
        }
    }

    internal fun mixFrames(frames: List<ByteArray>): ByteArray {
        if (frames.isEmpty()) return ByteArray(FRAME_BYTES)
        if (frames.size == 1) return frames[0].copyOf()

        val out = ByteArray(FRAME_BYTES)
        var i = 0
        while (i + 1 < FRAME_BYTES) {
            var sum = 0
            var contributors = 0
            for (frame in frames) {
                if (i + 1 >= frame.size) continue
                val lo = frame[i].toInt() and 0xff
                val hi = frame[i + 1].toInt()
                sum += ((hi shl 8) or lo).toShort().toInt()
                contributors++
            }
            val mixed = if (contributors == 0) 0 else (sum / contributors)
                .coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt())
            out[i] = (mixed and 0xff).toByte()
            out[i + 1] = ((mixed shr 8) and 0xff).toByte()
            i += 2
        }
        return out
    }

    fun release() {
        stopTransmit()
        playbackRunning.set(false)
        playbackThread.interrupt()
        sourceQueues.clear()
        sourcePrimed.clear()
        sourceLastSeenMs.clear()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            try { audioManager.clearCommunicationDevice() } catch (_: Throwable) {}
        } else {
            @Suppress("DEPRECATION")
            try {
                audioManager.stopBluetoothSco()
                audioManager.isBluetoothScoOn = false
                audioManager.isSpeakerphoneOn = false
            } catch (_: Throwable) {}
        }
        audioTrack?.let {
            try { it.stop() } catch (_: Throwable) {}
            it.release()
        }
        audioTrack = null
        try { audioManager.mode = AudioManager.MODE_NORMAL } catch (_: Throwable) {}
    }

    private fun ensureTrack(): AudioTrack? {
        audioTrack?.let { return it }

        return try {
            val min = AudioTrack.getMinBufferSize(SAMPLE_RATE, CHANNEL_OUT, ENCODING)
            if (min <= 0) return null

            val track = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setSampleRate(SAMPLE_RATE)
                        .setEncoding(ENCODING)
                        .setChannelMask(CHANNEL_OUT)
                        .build()
                )
                .setBufferSizeInBytes(max(min, FRAME_BYTES * 3))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            if (track.state != AudioTrack.STATE_INITIALIZED) {
                track.release()
                null
            } else {
                track.play()
                audioTrack = track
                track
            }
        } catch (_: Throwable) {
            null
        }
    }

    private fun pcmRms(bytes: ByteArray): Double {
        if (bytes.size < 2) return 0.0
        var sum = 0.0
        var samples = 0
        var i = 0
        while (i + 1 < bytes.size) {
            val lo = bytes[i].toInt() and 0xff
            val hi = bytes[i + 1].toInt()
            val sample = ((hi shl 8) or lo).toShort().toInt()
            sum += sample.toDouble() * sample.toDouble()
            samples++
            i += 2
        }
        return if (samples == 0) 0.0 else sqrt(sum / samples)
    }

    private fun createAec(sessionId: Int): AcousticEchoCanceler? = try {
        if (AcousticEchoCanceler.isAvailable()) {
            AcousticEchoCanceler.create(sessionId)?.apply { enabled = true }
        } else null
    } catch (_: Throwable) { null }

    private fun createNs(sessionId: Int): NoiseSuppressor? = try {
        if (NoiseSuppressor.isAvailable()) {
            NoiseSuppressor.create(sessionId)?.apply { enabled = true }
        } else null
    } catch (_: Throwable) { null }

    private fun createAgc(sessionId: Int): AutomaticGainControl? = try {
        if (AutomaticGainControl.isAvailable()) {
            AutomaticGainControl.create(sessionId)?.apply { enabled = true }
        } else null
    } catch (_: Throwable) { null }

    private fun effectsLabel(aec: Boolean, ns: Boolean, agc: Boolean): String {
        val enabled = buildList {
            if (aec) add("AEC")
            if (ns) add("NS")
            if (agc) add("AGC")
        }
        return if (enabled.isEmpty()) "software wind filter" else enabled.joinToString("+") + "+WIND"
    }

    private class WindRumbleFilter(sampleRate: Int, cutoffHz: Double) {
        private val alpha: Double
        private var previousInput = 0.0
        private var previousOutput = 0.0

        init {
            val dt = 1.0 / sampleRate.toDouble()
            val rc = 1.0 / (2.0 * PI * cutoffHz)
            alpha = rc / (rc + dt)
        }

        fun process(bytes: ByteArray): ByteArray {
            if (bytes.size < 2) return bytes
            val out = bytes.copyOf()
            var i = 0
            while (i + 1 < bytes.size) {
                val lo = bytes[i].toInt() and 0xff
                val hi = bytes[i + 1].toInt()
                val input = ((hi shl 8) or lo).toShort().toDouble()
                val filtered = alpha * (previousOutput + input - previousInput)
                previousInput = input
                previousOutput = filtered
                val sample = filtered.toInt().coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt())
                out[i] = (sample and 0xff).toByte()
                out[i + 1] = ((sample shr 8) and 0xff).toByte()
                i += 2
            }
            return out
        }
    }

    private fun AudioDeviceInfo.isHelmetCandidate(): Boolean {
        return when (type) {
            AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
            AudioDeviceInfo.TYPE_BLE_HEADSET,
            AudioDeviceInfo.TYPE_HEARING_AID -> true
            else -> false
        }
    }

    private fun AudioDeviceInfo.routeLabel(): String {
        return when {
            isHelmetCandidate() -> productName?.toString()?.takeIf { it.isNotBlank() }
                ?: "Bluetooth helmet/headset"
            type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER -> "phone speaker + microphone"
            else -> productName?.toString()?.takeIf { it.isNotBlank() } ?: "communication device"
        }
    }

    companion object {
        private const val SAMPLE_RATE = 16_000
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
        private const val CHANNEL_IN = AudioFormat.CHANNEL_IN_MONO
        private const val CHANNEL_OUT = AudioFormat.CHANNEL_OUT_MONO
        private const val FRAME_MS = 20
        private const val SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS / 1000
        internal const val FRAME_BYTES = SAMPLES_PER_FRAME * 2

        private const val SOURCE_QUEUE_MAX_FRAMES = 3 // ~60 ms maximum per remote rider
        private const val SOURCE_PRIME_FRAMES = 2     // ~40 ms jitter buffer
        private const val SOURCE_EXPIRE_MS = 2_000L
        private const val PLAYBACK_IDLE_SLEEP_MS = 4L
        private const val ECHO_GUARD_AFTER_PLAYBACK_MS = 100L

        private const val VAD_PREROLL_FRAMES = 3
        private const val VAD_HANGOVER_FRAMES = 8 // 160 ms; shorter to reduce echo tails
        private const val VAD_INITIAL_NOISE_FLOOR = 250.0
        private const val VAD_MIN_RMS = 520.0
        private const val VAD_NOISE_MULTIPLIER = 2.2
        private const val VAD_ECHO_MIN_RMS_AEC = 1_800.0
        private const val VAD_ECHO_MIN_RMS_NO_AEC = 3_200.0
        private const val VAD_ECHO_MULTIPLIER_AEC = 2.4
        private const val VAD_ECHO_MULTIPLIER_NO_AEC = 3.4
        private const val WIND_FILTER_CUTOFF_HZ = 110.0
    }
}
