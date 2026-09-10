package com.bikemesh.ridemesh.offline

import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Packs two 20 ms PCM frames into one 40 ms realtime voice payload.
 * This halves Nearby BYTES payload frequency while preserving every sample.
 */
object RealtimeVoicePacket {
    private const val MAGIC = 0x52565031 // RVP1
    private const val VERSION: Byte = 1
    const val FRAME_BYTES = 640
    const val FRAMES_PER_PACKET = 2
    const val PACKET_AUDIO_BYTES = FRAME_BYTES * FRAMES_PER_PACKET
    private const val HEADER_BYTES = 8

    fun encode(frameA: ByteArray, frameB: ByteArray): ByteArray {
        require(frameA.size == FRAME_BYTES && frameB.size == FRAME_BYTES)
        val out = ByteBuffer.allocate(HEADER_BYTES + PACKET_AUDIO_BYTES).order(ByteOrder.BIG_ENDIAN)
        out.putInt(MAGIC)
        out.put(VERSION)
        out.put(FRAMES_PER_PACKET.toByte())
        out.putShort(FRAME_BYTES.toShort())
        out.put(frameA)
        out.put(frameB)
        return out.array()
    }

    fun decode(payload: ByteArray): List<ByteArray>? = runCatching {
        if (payload.size != HEADER_BYTES + PACKET_AUDIO_BYTES) return null
        val input = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)
        if (input.int != MAGIC || input.get() != VERSION) return null
        if ((input.get().toInt() and 0xff) != FRAMES_PER_PACKET) return null
        if ((input.short.toInt() and 0xffff) != FRAME_BYTES) return null
        val a = ByteArray(FRAME_BYTES)
        val b = ByteArray(FRAME_BYTES)
        input.get(a)
        input.get(b)
        listOf(a, b)
    }.getOrNull()
}
