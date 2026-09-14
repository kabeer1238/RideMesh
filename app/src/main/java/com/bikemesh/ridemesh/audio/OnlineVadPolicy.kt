package com.bikemesh.ridemesh.audio

/** Pure policy: 100 ms lookahead and 500 ms release. No network or microphone ownership. */
internal object OnlineVadPolicy {
    const val LOOKAHEAD_FRAMES = 10 // WebRTC supplies 10 ms PCM frames.
    const val HANGOVER_SAMPLES = 8_000L // 500 ms at the analysis rate of 16 kHz.
    const val DECISION_LOOKAHEAD = 640L // 40 ms: covers one 32 ms Silero window.
    const val WARMUP_SAMPLES = 16_000L

    fun pass(endSample: Long, processed: Long, speechThrough: Long): Boolean =
        endSample <= WARMUP_SAMPLES ||
            processed < endSample + DECISION_LOOKAHEAD ||
            endSample <= speechThrough

    /** Analysis-only conversion. Original transmitted PCM retains its native sample rate.
     * Integer-rate averaging for 32/48 kHz; duplication for 8 kHz. Never used for playback.
     */
    fun analysisFrame(input: ByteArray, rate: Int): ByteArray {
        require(rate in intArrayOf(8_000, 16_000, 32_000, 48_000))
        require(input.size == rate / 100 * 2)
        fun sample(index: Int): Int =
            ((input[index * 2].toInt() and 255) or
                (input[index * 2 + 1].toInt() shl 8)).toShort().toInt()
        val output = ByteArray(320)
        for (i in 0 until 160) {
            val value = if (rate == 8_000) sample(i / 2) else {
                val ratio = rate / 16_000
                var sum = 0
                for (j in 0 until ratio) sum += sample(i * ratio + j)
                sum / ratio
            }
            output[i * 2] = value.toByte()
            output[i * 2 + 1] = (value shr 8).toByte()
        }
        return output
    }
}
