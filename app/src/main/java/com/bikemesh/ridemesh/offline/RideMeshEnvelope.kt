package com.bikemesh.ridemesh.offline

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

/**
 * Transport-neutral RideMesh offline envelope.
 *
 * Nearby is only the link layer. This envelope is owned by RideMesh and is the
 * unit that can later be carried by Nearby, Internet, Wi-Fi Aware, or another
 * transport without changing routing identity.
 */
data class RideMeshEnvelope(
    val messageId: UUID,
    val originNodeId: UUID,
    val previousHopNodeId: UUID,
    val sequence: Int,
    val createdAtMs: Long,
    val ttl: Int,
    val hopCount: Int,
    val type: Type,
    val payload: ByteArray,
) {
    enum class Type(val wire: Int) {
        DIAGNOSTIC(1),
        AUDIO(2),
        PRESENCE(3),
        CONTROL(4);

        companion object {
            fun fromWire(value: Int): Type? = entries.firstOrNull { it.wire == value }
        }
    }

    fun forwardedBy(nodeId: UUID): RideMeshEnvelope? {
        if (ttl <= 0) return null
        return copy(
            previousHopNodeId = nodeId,
            ttl = ttl - 1,
            hopCount = (hopCount + 1).coerceAtMost(255),
        )
    }

    fun encode(): ByteArray {
        require(payload.size <= MAX_PAYLOAD) { "RideMesh envelope payload too large" }
        require(ttl in 0..255)
        require(hopCount in 0..255)

        val out = ByteBuffer.allocate(HEADER_SIZE + payload.size).order(ByteOrder.BIG_ENDIAN)
        out.putInt(MAGIC)
        out.put(VERSION)
        out.put(type.wire.toByte())
        out.put(ttl.toByte())
        out.put(hopCount.toByte())
        putUuid(out, messageId)
        putUuid(out, originNodeId)
        putUuid(out, previousHopNodeId)
        out.putInt(sequence)
        out.putLong(createdAtMs)
        out.putInt(payload.size)
        out.put(payload)
        return out.array()
    }

    companion object {
        private const val MAGIC = 0x524D4531 // RME1
        private const val VERSION: Byte = 1
        private const val HEADER_SIZE = 72
        const val MAX_PAYLOAD = 256 * 1024

        fun decode(bytes: ByteArray): RideMeshEnvelope? = runCatching {
            if (bytes.size < HEADER_SIZE) return null
            val input = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
            if (input.int != MAGIC) return null
            if (input.get() != VERSION) return null
            val type = Type.fromWire(input.get().toInt() and 0xff) ?: return null
            val ttl = input.get().toInt() and 0xff
            val hops = input.get().toInt() and 0xff
            val messageId = getUuid(input)
            val origin = getUuid(input)
            val previousHop = getUuid(input)
            val sequence = input.int
            val createdAt = input.long
            val payloadSize = input.int
            if (payloadSize < 0 || payloadSize > MAX_PAYLOAD || payloadSize != input.remaining()) return null
            val payload = ByteArray(payloadSize)
            input.get(payload)
            RideMeshEnvelope(messageId, origin, previousHop, sequence, createdAt, ttl, hops, type, payload)
        }.getOrNull()

        fun newDiagnostic(nodeId: UUID, sequence: Int, text: String, ttl: Int = 4): RideMeshEnvelope =
            RideMeshEnvelope(
                messageId = UUID.randomUUID(),
                originNodeId = nodeId,
                previousHopNodeId = nodeId,
                sequence = sequence,
                createdAtMs = System.currentTimeMillis(),
                ttl = ttl.coerceIn(0, 255),
                hopCount = 0,
                type = Type.DIAGNOSTIC,
                payload = text.toByteArray(Charsets.UTF_8),
            )

        private fun putUuid(buffer: ByteBuffer, uuid: UUID) {
            buffer.putLong(uuid.mostSignificantBits)
            buffer.putLong(uuid.leastSignificantBits)
        }

        private fun getUuid(buffer: ByteBuffer): UUID = UUID(buffer.long, buffer.long)
    }
}
