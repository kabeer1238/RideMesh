package com.bikemesh.ridemesh.audio

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.os.Process
import java.util.ArrayDeque
import java.util.TreeMap
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.PI
import kotlin.math.abs
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
    private val transmitDesired = AtomicBoolean(false)
    private val focusPaused = AtomicBoolean(false)
    private val focusHeld = AtomicBoolean(false)
    private val userMuted = AtomicBoolean(false)

    private data class IncomingFrame(
        val sequence: Int,
        val timestampMs: Long,
        val arrivalMs: Long,
        val audio: ByteArray,
    )

    private class SourceState {
        val frames = TreeMap<Int, IncomingFrame>()
        var expectedSequence: Int? = null
        var primed = false
        var targetPrimeFrames = MIN_PRIME_FRAMES
        var jitterEwmaMs = 0.0
        var lastArrivalMs = 0L
        var lastSenderTimestampMs = 0L
        var lastSeenMs = 0L
        var lastGoodFrame: ByteArray? = null
        var consecutivePlc = 0
    }

    /**
     * Beta3 keeps an ordered adaptive jitter buffer for each rider. Good links stay at
     * about 40 ms of prebuffer; unstable links can expand toward 120 ms temporarily.
     */
    private val sourceStates = ConcurrentHashMap<String, SourceState>()

    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var audioTrack: AudioTrack? = null
    @Volatile private var route: AudioRoute = AudioRoute.AUTO
    @Volatile private var playbackActiveUntilMs = 0L

    private val playbackThread = Thread({ playbackLoop() }, "RideMesh-Mixer").apply {
        isDaemon = true
        start()
    }

    private val voiceAttributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()

    private val audioFocusListener = AudioManager.OnAudioFocusChangeListener { change ->
        when (change) {
            AudioManager.AUDIOFOCUS_GAIN -> resumeAfterAudioFocus()
            AudioManager.AUDIOFOCUS_LOSS,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> pauseForAudioFocus()
        }
    }

    private val audioFocusRequest: AudioFocusRequest by lazy {
        AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(voiceAttributes)
            .setAcceptsDelayedFocusGain(true)
            .setWillPauseWhenDucked(true)
            .setOnAudioFocusChangeListener(audioFocusListener)
            .build()
    }

    private fun ensureAudioFocus(): Boolean {
        if (focusHeld.get() && focusPaused.get()) return false
        if (focusHeld.get() && !focusPaused.get()) return true
        return when (audioManager.requestAudioFocus(audioFocusRequest)) {
            AudioManager.AUDIOFOCUS_REQUEST_GRANTED -> {
                focusHeld.set(true)
                focusPaused.set(false)
                true
            }
            AudioManager.AUDIOFOCUS_REQUEST_DELAYED -> {
                focusHeld.set(true)
                focusPaused.set(true)
                onStatus("PAUSED FOR PHONE CALL • AUTO RESUME")
                false
            }
            else -> {
                focusHeld.set(false)
                focusPaused.set(true)
                onStatus("AUDIO BUSY • WAITING TO RESUME")
                false
            }
        }
    }

    private fun pauseForAudioFocus() {
        focusPaused.set(true)
        capturing.set(false)
        clearRemoteAudio()
        audioTrack?.let {
            try { it.pause() } catch (_: Throwable) {}
            try { it.flush() } catch (_: Throwable) {}
        }
        onStatus("PAUSED FOR PHONE CALL • AUTO RESUME")
    }

    private fun resumeAfterAudioFocus() {
        focusHeld.set(true)
        focusPaused.set(false)
        selectCommunicationDevice()
        audioTrack?.let {
            try { it.play() } catch (_: Throwable) {}
        }
        onStatus("HANDS-FREE • AUDIO RESUMED")
        if (transmitDesired.get()) startRecorder()
    }

    private fun clearRemoteAudio() {
        sourceStates.values.forEach { state ->
            synchronized(state) {
                state.frames.clear()
                state.expectedSequence = null
                state.primed = false
                state.lastGoodFrame = null
                state.consecutivePlc = 0
            }
        }
        sourceStates.clear()
    }

    fun setRoute(newRoute: AudioRoute) {
        route = newRoute
    }

    fun setUserMuted(muted: Boolean) {
        userMuted.set(muted)
        if (muted) {
            onStatus("MIC MUTED • LISTENING ONLY")
        } else {
            onStatus("HANDS-FREE • MIC LIVE")
        }
    }

    fun isUserMuted(): Boolean = userMuted.get()

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
        transmitDesired.set(true)
        if (!ensureAudioFocus() || focusPaused.get()) return
        startRecorder()
    }

    @SuppressLint("MissingPermission")
    private fun startRecorder() {
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
            val recordBuffer = max(min, FRAME_BYTES * 2)

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
                Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
                val frame = ByteArray(FRAME_BYTES)
                val preRoll = ArrayDeque<ByteArray>(VAD_PREROLL_FRAMES)
                val windFilter = WindRumbleFilter(SAMPLE_RATE, WIND_FILTER_CUTOFF_HZ)
                var hangover = 0
                var wasSending = false
                var noiseFloor = VAD_INITIAL_NOISE_FLOOR

                try {
                    while (capturing.get()) {
                        // AudioRecord is allowed to return a partial buffer. Beta2 treated every
                        // partial read as a complete 20 ms packet, which can sound slow/choppy.
                        // Beta3 accumulates exactly one 20 ms frame before VAD/transmission.
                        var filled = 0
                        while (filled < frame.size && capturing.get()) {
                            val read = activeRecorder.read(
                                frame,
                                filled,
                                frame.size - filled,
                                AudioRecord.READ_BLOCKING,
                            )
                            if (read < 0) throw IllegalStateException("AudioRecord read error $read")
                            if (read == 0) continue
                            filled += read
                        }
                        if (filled != frame.size) continue

                        val current = windFilter.process(frame.copyOf())
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

                        // A manual mute keeps the recorder alive for instant recovery but sends no frames.
                        // Clear pre-roll/hangover so speech recorded while muted can never leak after unmuting.
                        if (userMuted.get()) {
                            preRoll.clear()
                            hangover = 0
                            wasSending = false
                            if (!farEndAudioActive) {
                                noiseFloor = (noiseFloor * 0.985) + (rms * 0.015)
                            }
                            continue
                        }

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
                    if (!focusPaused.get()) selectCommunicationDevice()
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
        transmitDesired.set(false)
        capturing.set(false)
    }

    /**
     * Add one sequenced 20 ms packet to the per-rider adaptive jitter buffer.
     * Sender timestamps are used only for inter-packet timing, never for wall-clock sync.
     */
    fun playIncoming(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {
        if (audio.isEmpty() || !playbackRunning.get() || focusPaused.get()) return
        val key = sourceId.ifBlank { "unknown" }
        val normalized = when {
            audio.size == FRAME_BYTES -> audio.copyOf()
            audio.size > FRAME_BYTES -> audio.copyOf(FRAME_BYTES)
            else -> audio.copyOf(FRAME_BYTES)
        }
        val now = System.currentTimeMillis()
        val state = sourceStates.computeIfAbsent(key) { SourceState() }

        synchronized(state) {
            if (state.lastArrivalMs > 0L && state.lastSenderTimestampMs > 0L) {
                val arrivalDelta = now - state.lastArrivalMs
                val senderDelta = timestampMs - state.lastSenderTimestampMs
                if (arrivalDelta in 0L..500L && senderDelta in 10L..200L) {
                    val sample = abs(arrivalDelta.toDouble() - senderDelta.toDouble())
                    state.jitterEwmaMs = if (state.jitterEwmaMs == 0.0) {
                        sample
                    } else {
                        (state.jitterEwmaMs * 0.88) + (sample * 0.12)
                    }
                    state.targetPrimeFrames = targetPrimeFrames(state.jitterEwmaMs)
                }
            }

            state.lastArrivalMs = now
            state.lastSenderTimestampMs = timestampMs
            state.lastSeenMs = now

            val expected = state.expectedSequence
            if (expected != null && sequence < expected - OLD_PACKET_TOLERANCE) return@synchronized
            if (!state.frames.containsKey(sequence)) {
                state.frames[sequence] = IncomingFrame(sequence, timestampMs, now, normalized)
            }

            while (state.frames.size > MAX_SOURCE_QUEUE_FRAMES) {
                state.frames.pollFirstEntry()
            }

            // If the receiver ever gets far behind, jump forward rather than playing old speech.
            if (state.primed && state.frames.size > state.targetPrimeFrames + LATENCY_CATCHUP_MARGIN) {
                while (state.frames.size > state.targetPrimeFrames) state.frames.pollFirstEntry()
                state.expectedSequence = state.frames.firstKey()
                state.consecutivePlc = 0
            }
        }
    }

    private fun playbackLoop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
        var nextTickNs = System.nanoTime()

        while (playbackRunning.get()) {
            try {
                if (focusPaused.get()) {
                    Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                    nextTickNs = System.nanoTime()
                    continue
                }

                val nowNs = System.nanoTime()
                if (nowNs < nextTickNs) {
                    sleepNanos(nextTickNs - nowNs)
                } else if (nowNs - nextTickNs > FRAME_NS * 3) {
                    // Do not attempt to replay missed scheduler time after a stall.
                    nextTickNs = nowNs
                }
                nextTickNs += FRAME_NS

                val nowMs = System.currentTimeMillis()
                val frames = ArrayList<ByteArray>(sourceStates.size)
                var activeSource = false

                for ((sourceId, state) in sourceStates) {
                    val frame = synchronized(state) { pullPlayoutFrame(state, nowMs) }
                    if (frame != null) frames.add(frame)
                    if (nowMs - state.lastSeenMs <= SOURCE_SILENCE_HOLD_MS) activeSource = true

                    if (nowMs - state.lastSeenMs > SOURCE_EXPIRE_MS && synchronized(state) { state.frames.isEmpty() }) {
                        sourceStates.remove(sourceId, state)
                    }
                }

                if (frames.isEmpty() && !activeSource) {
                    Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                    nextTickNs = System.nanoTime() + FRAME_NS
                    continue
                }

                // Keep the AudioTrack clock moving at a fixed 20 ms cadence between voice packets.
                val mixed = if (frames.isEmpty()) SILENCE_FRAME else mixFrames(frames)
                val track = ensureTrack() ?: continue
                playbackActiveUntilMs = nowMs + ECHO_GUARD_AFTER_PLAYBACK_MS
                track.write(mixed, 0, mixed.size, AudioTrack.WRITE_BLOCKING)
            } catch (_: InterruptedException) {
                break
            } catch (_: Throwable) {
                Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                nextTickNs = System.nanoTime() + FRAME_NS
            }
        }
    }

    private fun pullPlayoutFrame(state: SourceState, nowMs: Long): ByteArray? {
        while (state.frames.isNotEmpty()) {
            val expected = state.expectedSequence ?: break
            if (state.frames.firstKey() < expected) state.frames.pollFirstEntry() else break
        }

        if (!state.primed) {
            if (state.frames.size < state.targetPrimeFrames) return null
            state.expectedSequence = state.frames.firstKey()
            state.primed = true
        }

        var expected = state.expectedSequence ?: return null
        val exact = state.frames.remove(expected)
        if (exact != null) {
            state.expectedSequence = expected + 1
            state.lastGoodFrame = exact.audio
            state.consecutivePlc = 0
            return exact.audio
        }

        if (state.frames.isNotEmpty()) {
            val next = state.frames.firstKey()
            val gap = next - expected
            if (gap > 0 && gap <= MAX_PLC_GAP_FRAMES && state.consecutivePlc < MAX_PLC_GAP_FRAMES) {
                state.expectedSequence = expected + 1
                state.consecutivePlc++
                return concealFrame(state.lastGoodFrame, state.consecutivePlc)
            }

            // Large gap or sequence reset: resync immediately to the freshest available packet.
            if (gap > MAX_PLC_GAP_FRAMES || gap < -OLD_PACKET_TOLERANCE) {
                state.expectedSequence = next
                state.consecutivePlc = 0
                expected = next
                val fresh = state.frames.remove(expected)
                if (fresh != null) {
                    state.expectedSequence = expected + 1
                    state.lastGoodFrame = fresh.audio
                    return fresh.audio
                }
            }
        }

        // One very short concealment frame is allowed while waiting for a genuinely late packet.
        if (nowMs - state.lastSeenMs <= LATE_PACKET_GRACE_MS && state.consecutivePlc < 1) {
            state.expectedSequence = expected + 1
            state.consecutivePlc++
            return concealFrame(state.lastGoodFrame, state.consecutivePlc)
        }
        return null
    }

    private fun concealFrame(previous: ByteArray?, lossIndex: Int): ByteArray? {
        previous ?: return null
        val gain = if (lossIndex <= 1) 0.62 else 0.38
        val out = previous.copyOf()
        var i = 0
        while (i + 1 < out.size) {
            val lo = out[i].toInt() and 0xff
            val hi = out[i + 1].toInt()
            val sample = ((hi shl 8) or lo).toShort().toInt()
            val faded = (sample * gain).toInt().coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt())
            out[i] = (faded and 0xff).toByte()
            out[i + 1] = ((faded shr 8) and 0xff).toByte()
            i += 2
        }
        return out
    }

    private fun targetPrimeFrames(jitterMs: Double): Int = when {
        jitterMs < 7.0 -> 2
        jitterMs < 15.0 -> 3
        jitterMs < 28.0 -> 4
        jitterMs < 45.0 -> 5
        else -> 6
    }

    private fun sleepNanos(nanos: Long) {
        if (nanos <= 0L) return
        val millis = nanos / 1_000_000L
        val extraNanos = (nanos % 1_000_000L).toInt()
        Thread.sleep(millis, extraNanos)
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
        sourceStates.clear()
        if (focusHeld.getAndSet(false)) {
            try { audioManager.abandonAudioFocusRequest(audioFocusRequest) } catch (_: Throwable) {}
        }
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
                .setBufferSizeInBytes(max(min, FRAME_BYTES * 2))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
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

        private const val MIN_PRIME_FRAMES = 2          // 40 ms on a clean link
        private const val MAX_SOURCE_QUEUE_FRAMES = 8   // hard cap: 160 ms
        private const val LATENCY_CATCHUP_MARGIN = 2
        private const val MAX_PLC_GAP_FRAMES = 2        // conceal at most 40 ms
        private const val OLD_PACKET_TOLERANCE = 32
        private const val SOURCE_EXPIRE_MS = 2_000L
        private const val SOURCE_SILENCE_HOLD_MS = 320L
        private const val LATE_PACKET_GRACE_MS = 45L
        private const val PLAYBACK_IDLE_SLEEP_MS = 3L
        private const val ECHO_GUARD_AFTER_PLAYBACK_MS = 100L
        private const val FRAME_NS = FRAME_MS * 1_000_000L
        private val SILENCE_FRAME = ByteArray(FRAME_BYTES)

        private const val VAD_PREROLL_FRAMES = 2
        private const val VAD_HANGOVER_FRAMES = 5 // 100 ms: fast close without clipping word endings
        private const val VAD_INITIAL_NOISE_FLOOR = 250.0
        private const val VAD_MIN_RMS = 480.0
        private const val VAD_NOISE_MULTIPLIER = 2.05
        private const val VAD_ECHO_MIN_RMS_AEC = 1_800.0
        private const val VAD_ECHO_MIN_RMS_NO_AEC = 3_200.0
        private const val VAD_ECHO_MULTIPLIER_AEC = 2.4
        private const val VAD_ECHO_MULTIPLIER_NO_AEC = 3.4
        private const val WIND_FILTER_CUTOFF_HZ = 110.0
    }
}
