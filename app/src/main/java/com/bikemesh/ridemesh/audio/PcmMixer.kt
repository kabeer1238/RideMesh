package com.bikemesh.ridemesh.audio

import kotlin.math.abs
import kotlin.math.roundToInt

/**
 * Mix PCM16 mono without dividing speech by the number of connected riders.
 * A frame-wide limiter preserves waveform shape when simultaneous speech overloads.
 * This is not a VAD: quiet syllables are retained, and no loudness-based speaker
 * selection can mistake helmet wind for the only rider allowed to speak.
 */
internal object PcmMixer {
    fun mix(frames: List<ByteArray>, frameBytes: Int): ByteArray {
        require(frameBytes >= 0 && frameBytes % 2 == 0)
        val sums = IntArray(frameBytes / 2)
        for (frame in frames) {
            for (i in 0 until minOf(sums.size, frame.size / 2)) {
                val sample = ((frame[i * 2].toInt() and 255) or
                    (frame[i * 2 + 1].toInt() shl 8)).toShort().toInt()
                sums[i] += sample
            }
        }
        val peak = sums.maxOfOrNull { abs(it) } ?: 0
        val gain = if (peak > 32767) 32767.0 / peak else 1.0
        val out = ByteArray(frameBytes)
        for (i in sums.indices) {
            val sample = (sums[i] * gain).roundToInt().coerceIn(-32768, 32767)
            out[i * 2] = sample.toByte()
            out[i * 2 + 1] = (sample shr 8).toByte()
        }
        return out
    }
}
