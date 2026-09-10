package com.bikemesh.ridemesh.offline

import java.util.LinkedHashMap
import java.util.UUID
import java.util.concurrent.atomic.AtomicInteger

/**
 * RideMesh application-level relay/dedup layer.
 *
 * Nearby is only the direct-neighbor link. This router owns message identity,
 * duplicate suppression, TTL and hop-count forwarding. Diagnostic and audio
 * packets use the same RME1 envelope so the exact voice packets tested on a
 * two-device link can later be relayed A -> B -> C without changing format.
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
        val envelope = newEnvelope(
            type = RideMeshEnvelope.Type.DIAGNOSTIC,
            payload = text.toByteArray(Charsets.UTF_8),
            ttl = ttl,
        )
        remember(envelope.messageId)
        onDeliver(envelope)
        return sendToNeighborsExcept(null, envelope.encode())
    }

    /**
     * Originates one encoded/raw 20 ms audio frame. For the first field voice
     * milestone the payload is the existing AudioEngine PCM frame. A later Opus
     * codec can replace only the payload while keeping this envelope/router intact.
     */
    fun originateAudio(frame: ByteArray, ttl: Int = DEFAULT_TTL): Boolean {
        if (frame.isEmpty()) return false
        val envelope = newEnvelope(
            type = RideMeshEnvelope.Type.AUDIO,
            payload = frame.copyOf(),
            ttl = ttl,
        )
        remember(envelope.messageId)
        // Do not deliver our own microphone frame back to local playback.
        return sendToNeighborsExcept(null, envelope.encode())
    }

    fun receive(fromNodeId: String, bytes: ByteArray) {
        val envelope = RideMeshEnvelope.decode(bytes) ?: run {
            onStatus("ROUTER DROP • invalid envelope from ${fromNodeId.take(8)}")
            return
        }

        if (!remember(envelope.messageId)) {
            // Audio duplicates are expected during a dense flood and should be
            // dropped quietly so UI/status is not spammed at 50 frames/second.
            if (envelope.type != RideMeshEnvelope.Type.AUDIO) {
                onStatus("ROUTER DEDUP • ${shortId(envelope.messageId)}")
            }
            return
        }

        onDeliver(envelope)

        if (envelope.originNodeId == localNodeId) return
        val forwarded = envelope.forwardedBy(localNodeId) ?: run {
            if (envelope.type != RideMeshEnvelope.Type.AUDIO) {
                onStatus("ROUTER TTL EXPIRED • ${shortId(envelope.messageId)}")
            }
            return
        }

        val sent = sendToNeighborsExcept(fromNodeId, forwarded.encode())
        if (sent && envelope.type != RideMeshEnvelope.Type.AUDIO) {
            onStatus("ROUTER RELAY • ${shortId(envelope.messageId)} • hop ${forwarded.hopCount} • ttl ${forwarded.ttl}")
        }
    }

    private fun newEnvelope(type: RideMeshEnvelope.Type, payload: ByteArray, ttl: Int): RideMeshEnvelope =
        RideMeshEnvelope(
            messageId = UUID.randomUUID(),
            originNodeId = localNodeId,
            previousHopNodeId = localNodeId,
            sequence = sequence.incrementAndGet(),
            createdAtMs = System.currentTimeMillis(),
            ttl = ttl.coerceIn(0, 255),
            hopCount = 0,
            type = type,
            payload = payload,
        )

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
