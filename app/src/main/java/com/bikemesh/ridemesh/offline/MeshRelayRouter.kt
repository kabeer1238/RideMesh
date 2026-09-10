package com.bikemesh.ridemesh.offline

import java.util.LinkedHashMap
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/**
 * RideMesh application-level relay/dedup layer.
 *
 * The transport provides direct neighbors. This router provides the first real
 * mesh behavior above it: stable message IDs, duplicate suppression, TTL and
 * hop-count forwarding. Audio will use the same path after codec/jitter work.
 */
class MeshRelayRouter(
    private val localNodeId: UUID,
    private val sendToNeighborsExcept: (excludedNodeId: String?, payload: ByteArray) -> Boolean,
    private val onDeliver: (RideMeshEnvelope) -> Unit,
    private val onStatus: (String) -> Unit,
) {
    private val sequence = AtomicInteger(0)
    private val lock = Any()
    private val seen = object : LinkedHashMap<UUID, Unit>(SEEN_LIMIT + 1, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<UUID, Unit>?): Boolean = size > SEEN_LIMIT
    }

    fun originateDiagnostic(text: String, ttl: Int = DEFAULT_TTL): Boolean {
        val envelope = RideMeshEnvelope.newDiagnostic(
            nodeId = localNodeId,
            sequence = sequence.incrementAndGet(),
            text = text,
            ttl = ttl,
        )
        remember(envelope.messageId)
        onDeliver(envelope)
        return sendToNeighborsExcept(null, envelope.encode())
    }

    fun receive(fromNodeId: String, bytes: ByteArray) {
        val envelope = RideMeshEnvelope.decode(bytes) ?: run {
            onStatus("ROUTER DROP • invalid envelope from ${fromNodeId.take(8)}")
            return
        }

        if (!remember(envelope.messageId)) {
            onStatus("ROUTER DEDUP • ${shortId(envelope.messageId)}")
            return
        }

        onDeliver(envelope)

        if (envelope.originNodeId == localNodeId) return
        val forwarded = envelope.forwardedBy(localNodeId) ?: run {
            onStatus("ROUTER TTL EXPIRED • ${shortId(envelope.messageId)}")
            return
        }

        val sent = sendToNeighborsExcept(fromNodeId, forwarded.encode())
        if (sent) {
            onStatus("ROUTER RELAY • ${shortId(envelope.messageId)} • hop ${forwarded.hopCount} • ttl ${forwarded.ttl}")
        }
    }

    private fun remember(id: UUID): Boolean = synchronized(lock) {
        if (seen.containsKey(id)) return@synchronized false
        seen[id] = Unit
        true
    }

    private fun shortId(id: UUID): String = id.toString().take(8)

    companion object {
        private const val DEFAULT_TTL = 4
        private const val SEEN_LIMIT = 2048
    }
}
