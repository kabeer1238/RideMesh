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
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.max

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
    private val playbackExecutor = Executors.newSingleThreadExecutor()

    @Volatile private var audioRecord: AudioRecord? = null
    @Volatile private var audioTrack: AudioTrack? = null
    @Volatile private var route: AudioRoute = AudioRoute.AUTO

    fun setRoute(newRoute: AudioRoute) {
        route = newRoute
    }

    @SuppressLint("MissingPermission")
    fun selectCommunicationDevice(): String {
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
                return text
            }

            val ok = audioManager.setCommunicationDevice(chosen)
            val label = chosen.routeLabel()
            val text = if (ok) "Audio: $label" else "Audio routing failed: $label"
            onStatus(text)
            return text
        }

        val hasBluetoothSco = audioManager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
            .any { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO }

        return try {
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
        } catch (t: Throwable) {
            val text = "Audio routing error: ${t.message ?: "unknown"}"
            onStatus(text)
            text
        }
    }

    @SuppressLint("MissingPermission")
    fun startTransmit() {
        if (!capturing.compareAndSet(false, true)) return
        selectCommunicationDevice()

        val min = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_IN, ENCODING)
        if (min <= 0) {
            capturing.set(false)
            onStatus("Microphone buffer unavailable")
            return
        }
        val recordBuffer = max(min, FRAME_BYTES * 4)

        val recorder = AudioRecord(
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
        onStatus("TRANSMITTING • ${effectsLabel(aec != null, ns != null, agc != null)}")

        Thread({
            val frame = ByteArray(FRAME_BYTES)
            try {
                while (capturing.get()) {
                    val read = recorder.read(frame, 0, frame.size)
                    if (read > 0) {
                        onCapturedFrame(if (read == frame.size) frame.copyOf() else frame.copyOf(read))
                    }
                }
            } finally {
                try { recorder.stop() } catch (_: Throwable) {}
                aec?.release()
                ns?.release()
                agc?.release()
                recorder.release()
                if (audioRecord === recorder) audioRecord = null
                selectCommunicationDevice()
            }
        }, "RideMesh-Mic").start()
    }

    fun stopTransmit() {
        capturing.set(false)
    }

    fun playIncoming(audio: ByteArray) {
        if (audio.isEmpty() || capturing.get()) return
        playbackExecutor.execute {
            val track = ensureTrack() ?: return@execute
            try {
                track.write(audio, 0, audio.size, AudioTrack.WRITE_BLOCKING)
            } catch (_: Throwable) {}
        }
    }

    fun release() {
        stopTransmit()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            audioManager.clearCommunicationDevice()
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
        audioManager.mode = AudioManager.MODE_NORMAL
        playbackExecutor.shutdownNow()
    }

    private fun ensureTrack(): AudioTrack? {
        audioTrack?.let { return it }

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
            .setBufferSizeInBytes(max(min, FRAME_BYTES * 8))
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()

        if (track.state != AudioTrack.STATE_INITIALIZED) {
            track.release()
            return null
        }

        track.play()
        audioTrack = track
        return track
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
        return if (enabled.isEmpty()) "voice processing unavailable" else enabled.joinToString("+")
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
        private const val FRAME_BYTES = SAMPLES_PER_FRAME * 2
    }
}
