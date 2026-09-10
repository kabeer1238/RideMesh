package com.bikemesh.ridemesh.offline

import android.content.Context
import com.bikemesh.ridemesh.transport.WifiAwareWireProtocol
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicLong

/** Dedicated Android offline coordinator. Existing online mesh and Maps stay untouched. */
class OfflineMeshController(
    context: Context,
    private val onLog: (String) -> Unit,
    private val onAudioFrame: (sourceNodeId: String, sequence: Int, timestampMs: Long, audio: ByteArray) -> Unit = { _, _, _, _ -> },
) : NearbyClusterTransport.Listener {

    data class PeerDetails(
        val nodeId: String,
        val riderName: String,
        val deviceName: String,
        val rttMs: Int?,
    )

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("ridemesh_offline_mesh", Context.MODE_PRIVATE)
    private val packetizerLock = Any()

    @Volatile private var cluster: NearbyClusterTransport? = null
    @Volatile private var router: MeshRelayRouter? = null
    @Volatile private var localNodeId: UUID? = null
    @Volatile private var lastPeerName: String? = null
    @Volatile private var lastRttMs: Int? = null
    @Volatile private var lastNearbyStatus: String = "NEARBY DIAG • NOT STARTED"
    @Volatile private var pendingPcmFrame: ByteArray? = null

    private val peerRttMs = ConcurrentHashMap<String, Int>()
    private val txAudioFrames = AtomicLong(0)
    private val rxAudioFrames = AtomicLong(0)
    private val congestionDroppedFrames = AtomicLong(0)

    fun start(riderName: String, rideCode: String, deviceName: String = "Android device") {
        stop()
        val normalizedCode = rideCode.trim().uppercase()
        if (normalizedCode.isBlank()) {
            lastNearbyStatus = "NEARBY DIAG • INVALID RIDE CODE"
            onLog("OFFLINE MESH • enter or scan a ride code first")
            return
        }
        val nodeIdText = prefs.getString(KEY_NODE_ID, null)
            ?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString().also { prefs.edit().putString(KEY_NODE_ID, it).apply() }
        val nodeId = runCatching { UUID.fromString(nodeIdText) }.getOrElse {
            UUID.randomUUID().also { replacement ->
                prefs.edit().putString(KEY_NODE_ID, replacement.toString()).apply()
            }
        }
        localNodeId = nodeId

        val token = WifiAwareWireProtocol.rideToken(normalizedCode)
        lastPeerName = null
        lastRttMs = null
        pendingPcmFrame = null
        peerRttMs.clear()
        txAudioFrames.set(0)
        rxAudioFrames.set(0)
        congestionDroppedFrames.set(0)
        lastNearbyStatus = "NEARBY DIAG • START REQUESTED"

        val newCluster = NearbyClusterTransport(
            context = appContext,
            nodeId = nodeId.toString(),
            riderName = riderName.ifBlank { "Rider" },
            rideToken = token,
            deviceName = deviceName.ifBlank { "Android device" },
            listener = this,
        )
        cluster = newCluster
        router = MeshRelayRouter(
            localNodeId = nodeId,
            sendToNeighborsExcept = { excludedNode, payload ->
                newCluster.sendExceptNode(excludedNode, payload)
            },
            onDeliver = { envelope ->
                when (envelope.type) {
                    RideMeshEnvelope.Type.AUDIO -> {
                        if (envelope.originNodeId != nodeId) {
                            val linkRtt = peerRttMs.values.maxOrNull() ?: lastRttMs ?: 0
                            if (linkRtt >= CONGESTION_HARD_RTT_MS) {
                                congestionDroppedFrames.addAndGet(RealtimeVoicePacket.FRAMES_PER_PACKET.toLong())
                            } else {
                                val frames = RealtimeVoicePacket.decode(envelope.payload)
                                    ?: envelope.payload.takeIf { it.size == RealtimeVoicePacket.FRAME_BYTES }?.let { listOf(it) }
                                    ?: emptyList()
                                frames.forEachIndexed { index, pcm ->
                                    rxAudioFrames.incrementAndGet()
                                    onAudioFrame(
                                        envelope.originNodeId.toString(),
                                        envelope.sequence * RealtimeVoicePacket.FRAMES_PER_PACKET + index,
                                        envelope.createdAtMs + (index * 20L),
                                        pcm,
                                    )
                                }
                            }
                        }
                    }
                    RideMeshEnvelope.Type.DIAGNOSTIC -> {
                        val text = envelope.payload.toString(Charsets.UTF_8).take(80)
                        onLog("MESH ENVELOPE • hop=${envelope.hopCount} ttl=${envelope.ttl} • $text")
                    }
                    else -> onLog("MESH ENVELOPE • ${envelope.type} • hop=${envelope.hopCount} ttl=${envelope.ttl}")
                }
            },
            onStatus = onLog,
        )
        newCluster.start()

        onLog("OFFLINE MESH ACTIVE • same-code Nearby P2P_CLUSTER • hotspot disabled")
        onLog("VOICE LOW-LATENCY • 40ms packets • congestion guard ${CONGESTION_SOFT_RTT_MS}ms")
        onLog("ROUTER READY • RME1 envelope • TTL 4 • dedup 2048")
    }

    fun stop() {
        cluster?.stop()
        cluster = null
        router = null
        localNodeId = null
        lastPeerName = null
        lastRttMs = null
        pendingPcmFrame = null
        peerRttMs.clear()
        txAudioFrames.set(0)
        rxAudioFrames.set(0)
        congestionDroppedFrames.set(0)
        lastNearbyStatus = "NEARBY DIAG • STOPPED"
    }

    fun isActive(): Boolean = cluster != null
    fun hotspotInvitePayload(): String? = null
    fun hotspotCredentialsSummary(): String? = null
    fun connectedPeerCount(): Int = cluster?.connectedPeerCount() ?: 0
    fun connectedPeerName(): String? = lastPeerName ?: cluster?.firstPeerName()
    fun currentRttMs(): Int? = lastRttMs
    fun diagnosticSummary(): String = lastNearbyStatus.removePrefix("NEARBY DIAG • ")
    fun audioTxCount(): Long = txAudioFrames.get()
    fun audioRxCount(): Long = rxAudioFrames.get()
    fun audioDropCount(): Long = congestionDroppedFrames.get()

    fun connectedPeerDetails(): List<PeerDetails> = cluster?.peerSnapshots()?.map { peer ->
        PeerDetails(
            nodeId = peer.nodeId,
            riderName = peer.riderName,
            deviceName = peer.deviceName,
            rttMs = peerRttMs[peer.nodeId],
        )
    } ?: emptyList()

    /** Sends a real RideMesh RME1 envelope, suitable for direct and relayed tests. */
    fun sendDiagnosticEnvelope(text: String): Boolean = router?.originateDiagnostic(text) == true

    /**
     * Accepts the existing 20 ms PCM capture frames, combines two into one 40 ms
     * network packet and stops feeding the reliable Nearby queue if RTT shows it
     * is falling behind. Live intercom drops stale speech instead of becoming
     * seconds late.
     */
    fun sendAudioFrame(audio: ByteArray): Boolean {
        if (audio.size != RealtimeVoicePacket.FRAME_BYTES) return false

        val rtt = lastRttMs ?: 0
        if (rtt >= CONGESTION_HARD_RTT_MS) {
            synchronized(packetizerLock) { pendingPcmFrame = null }
            congestionDroppedFrames.incrementAndGet()
            return false
        }

        val packet = synchronized(packetizerLock) {
            val first = pendingPcmFrame
            if (first == null) {
                pendingPcmFrame = audio.copyOf()
                null
            } else {
                pendingPcmFrame = null
                RealtimeVoicePacket.encode(first, audio)
            }
        } ?: return true

        // Begin shedding alternate 40 ms packets before the link reaches multi-second
        // queueing. This is intentionally lossy: fresh speech is more important than
        // perfect delivery in a realtime intercom.
        if (rtt >= CONGESTION_SOFT_RTT_MS && (txAudioFrames.get() / 2L) % 2L == 1L) {
            congestionDroppedFrames.addAndGet(2)
            return false
        }

        val sent = router?.originateAudio(packet) == true
        if (sent) txAudioFrames.addAndGet(2) else congestionDroppedFrames.addAndGet(2)
        return sent
    }

    override fun onStatus(message: String) {
        lastNearbyStatus = message
        onLog(message)
    }

    override fun onPeerConnected(nodeId: String, riderName: String) {
        lastPeerName = riderName.ifBlank { "Android rider" }
        lastNearbyStatus = "NEARBY DIAG • IDENTITY OK • $lastPeerName"
        onLog("OFFLINE ANDROID↔ANDROID CONNECTED • $lastPeerName")
        router?.originateDiagnostic("RIDEMESH_ROUTE_PROBE:${localNodeId.toString().take(8)}")
    }

    override fun onPeerDisconnected(nodeId: String) {
        peerRttMs.remove(nodeId)
        val peers = cluster?.peerSnapshots().orEmpty()
        lastPeerName = peers.firstOrNull()?.riderName
        lastRttMs = peers.firstOrNull()?.nodeId?.let(peerRttMs::get)
        lastNearbyStatus = "NEARBY DIAG • PEER LOST • REDISCOVERING"
        onLog("OFFLINE PEER LOST • automatic discovery/reconnect remains active")
    }

    override fun onRtt(nodeId: String, rttMs: Int) {
        val previousBucket = peerRttMs[nodeId]?.div(10)
        peerRttMs[nodeId] = rttMs
        lastRttMs = rttMs
        if (previousBucket != rttMs.div(10)) {
            val name = connectedPeerDetails().firstOrNull { it.nodeId == nodeId }?.riderName ?: lastPeerName ?: "peer"
            val congestion = if (rttMs >= CONGESTION_SOFT_RTT_MS) " • CONGESTION GUARD" else ""
            onLog("OFFLINE LINK • $name • ${rttMs}ms RTT$congestion")
        }
    }

    override fun onData(nodeId: String, payload: ByteArray) {
        router?.receive(nodeId, payload)
            ?: onLog("ROUTER DROP • router unavailable")
    }

    companion object {
        private const val KEY_NODE_ID = "node_id"
        private const val CONGESTION_SOFT_RTT_MS = 550
        private const val CONGESTION_HARD_RTT_MS = 900
    }
}
