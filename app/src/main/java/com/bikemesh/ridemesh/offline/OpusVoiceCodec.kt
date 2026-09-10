package com.bikemesh.ridemesh.offline

import org.concentus.OpusApplication
import org.concentus.OpusDecoder
import org.concentus.OpusEncoder
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ConcurrentHashMap

/**
 * Low-latency mono Opus codec for RideMesh offline voice.
 * Input/output PCM is 16 kHz, signed 16-bit little-endian, 20 ms (320 samples / 640 bytes).
 */
class OpusVoiceCodec {
    private val encodeLock = Any()
    private val encoder = OpusEncoder(SAMPLE_RATE, CHANNELS, OpusApplication.OPUS_APPLICATION_VOIP).apply {
        setBitrate(TARGET_BITRATE_BPS)
        setUseVBR(true)
        setUseConstrainedVBR(true)
        setUseInbandFEC(true)
        setPacketLossPercent(EXPECTED_PACKET_LOSS_PERCENT)
        setComplexity(ENCODER_COMPLEXITY)
    }

    private val decoders = ConcurrentHashMap<String, OpusDecoder>()

    fun encode20ms(pcm: ByteArray): ByteArray? {
        if (pcm.size != PCM_FRAME_BYTES) return null
        return runCatching {
            val out = ByteArray(MAX_OPUS_BYTES)
            val encoded = synchronized(encodeLock) {
                encoder.encode(pcm, 0, SAMPLES_PER_FRAME, out, 0, out.size)
            }
            if (encoded <= 0) return null
            ByteBuffer.allocate(HEADER_BYTES + encoded).order(ByteOrder.BIG_ENDIAN).apply {
                putInt(MAGIC)
                put(VERSION)
                putShort(encoded.toShort())
                put(out, 0, encoded)
            }.array()
        }.getOrNull()
    }

    fun decode20ms(sourceId: String, packet: ByteArray): ByteArray? {
        return runCatching {
            if (packet.size < HEADER_BYTES) return null
            val input = ByteBuffer.wrap(packet).order(ByteOrder.BIG_ENDIAN)
            if (input.int != MAGIC || input.get() != VERSION) return null
            val encodedBytes = input.short.toInt() and 0xffff
            if (encodedBytes <= 0 || encodedBytes != input.remaining() || encodedBytes > MAX_OPUS_BYTES) return null

            val opus = ByteArray(encodedBytes)
            input.get(opus)
            val decoder = decoders.computeIfAbsent(sourceId) { OpusDecoder(SAMPLE_RATE, CHANNELS) }
            val pcm = ByteArray(PCM_FRAME_BYTES)
            val samples = synchronized(decoder) {
                decoder.decode(opus, 0, opus.size, pcm, 0, SAMPLES_PER_FRAME, false)
            }
            if (samples <= 0) return null
            val bytes = (samples * CHANNELS * 2).coerceAtMost(pcm.size)
            if (bytes == PCM_FRAME_BYTES) pcm else pcm.copyOf(bytes).copyOf(PCM_FRAME_BYTES)
        }.getOrNull()
    }

    fun forgetPeer(sourceId: String) {
        decoders.remove(sourceId)
    }

    fun reset() {
        decoders.clear()
        synchronized(encodeLock) { encoder.resetState() }
    }

    companion object {
        const val SAMPLE_RATE = 16_000
        const val CHANNELS = 1
        const val FRAME_MS = 20
        const val SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS / 1000
        const val PCM_FRAME_BYTES = SAMPLES_PER_FRAME * 2
        const val TARGET_BITRATE_BPS = 20_000
        private const val EXPECTED_PACKET_LOSS_PERCENT = 10
        private const val ENCODER_COMPLEXITY = 7
        private const val MAX_OPUS_BYTES = 256
        private const val MAGIC = 0x4f505631 // OPV1
        private const val VERSION: Byte = 1
        private const val HEADER_BYTES = 7
    }
}
