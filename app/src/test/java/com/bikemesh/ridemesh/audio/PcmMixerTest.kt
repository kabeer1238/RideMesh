package com.bikemesh.ridemesh.audio

import org.junit.Assert.*
import org.junit.Test

class PcmMixerTest {
    private fun pcm(vararg values: Int): ByteArray = ByteArray(values.size * 2).also { out ->
        values.forEachIndexed { i, value ->
            out[i * 2] = value.toByte()
            out[i * 2 + 1] = (value shr 8).toByte()
        }
    }
    private fun samples(bytes: ByteArray) = IntArray(bytes.size / 2) { i ->
        ((bytes[i * 2].toInt() and 255) or (bytes[i * 2 + 1].toInt() shl 8)).toShort().toInt()
    }
    @Test fun silentRidersDoNotAttenuateSpeech() {
        val voice = pcm(1200, -2400, 300, 0)
        assertArrayEquals(voice, PcmMixer.mix(listOf(voice) + List(13) { ByteArray(8) }, 8))
    }
    @Test fun quietSyllablesArePreserved() {
        val voice = pcm(1, -1, 40, -40)
        assertArrayEquals(voice, PcmMixer.mix(listOf(voice), 8))
    }
    @Test fun simultaneousSpeechAddsWithoutWraparound() {
        val output = samples(PcmMixer.mix(listOf(pcm(30000, -30000), pcm(30000, -30000)), 4))
        assertEquals(32767, output[0])
        assertEquals(-32767, output[1])
    }
    @Test fun limiterPreservesRelativeWaveform() {
        val output = samples(PcmMixer.mix(listOf(pcm(30000, 15000), pcm(30000, 15000)), 4))
        assertEquals(32767, output[0])
        assertEquals(16384, output[1])
    }
    @Test fun shortAndOddFramesAreSafe() {
        assertArrayEquals(pcm(100, 0), PcmMixer.mix(listOf(pcm(100) + byteArrayOf(12)), 4))
        assertArrayEquals(ByteArray(4), PcmMixer.mix(emptyList(), 4))
    }
}
