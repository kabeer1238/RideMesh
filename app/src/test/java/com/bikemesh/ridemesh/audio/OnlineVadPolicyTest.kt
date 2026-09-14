package com.bikemesh.ridemesh.audio

import org.junit.Assert.*
import org.junit.Test

class OnlineVadPolicyTest {
    @Test fun warmupDoesNotGateFirstSpeech() {
        assertTrue(OnlineVadPolicy.pass(160, 1_600, -1))
        assertTrue(OnlineVadPolicy.pass(16_000, 20_000, -1))
    }

    @Test fun confirmedSilenceIsGatedAfterWarmup() {
        assertFalse(OnlineVadPolicy.pass(20_000, 21_600, -1))
    }

    @Test fun slowAnalysisFailsOpenInsteadOfDroppingSpeech() {
        assertTrue(OnlineVadPolicy.pass(20_000, 20_639, -1))
        assertFalse(OnlineVadPolicy.pass(20_000, 20_640, -1))
    }

    @Test fun lookaheadPreservesAudioBeforeDecisionAndHangoverPreservesPauses() {
        val speechDecision = 20_800L
        val through = speechDecision + OnlineVadPolicy.HANGOVER_SAMPLES
        assertTrue(OnlineVadPolicy.pass(20_000, 21_600, through))
        assertTrue(OnlineVadPolicy.pass(through, through + 640, through))
        assertFalse(OnlineVadPolicy.pass(through + 160, through + 800, through))
    }

    private fun constant(rate: Int, value: Int): ByteArray =
        ByteArray(rate / 100 * 2).also { pcm ->
            for (i in pcm.indices step 2) {
                pcm[i] = value.toByte()
                pcm[i + 1] = (value shr 8).toByte()
            }
        }

    @Test fun allSupportedRatesProduceTenMsAnalysisWithoutChangingInput() {
        for (rate in intArrayOf(8_000, 16_000, 32_000, 48_000)) {
            for (value in intArrayOf(-32768, -1234, 0, 1234, 32767)) {
                val input = constant(rate, value)
                val before = input.copyOf()
                assertArrayEquals(constant(16_000, value), OnlineVadPolicy.analysisFrame(input, rate))
                assertArrayEquals(before, input)
            }
        }
    }

    @Test fun downsampleAveragesRatherThanSelectingOneSample() {
        val input = ByteArray(960)
        for (i in input.indices step 6) {
            input[i] = 90
            input[i + 2] = 30
            input[i + 4] = 0
        }
        assertArrayEquals(constant(16_000, 40), OnlineVadPolicy.analysisFrame(input, 48_000))
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsUnsupportedRate() { OnlineVadPolicy.analysisFrame(ByteArray(882), 44_100) }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsPartialFrame() { OnlineVadPolicy.analysisFrame(ByteArray(318), 16_000) }
}
