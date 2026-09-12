package com.bikemesh.ridemesh.mesh

import android.content.Context
import com.bikemesh.ridemesh.offline.OfflineMeshController

/** Cyan UI adapter to the September 11 offline controller, codec and router. */
class MeshNode(private val context: Context, private val listener: Listener) {
    enum class LabRole { NORMAL, A, B, C, D, E, F, G, H }
    data class RiderPeer(val endpointId: String, val riderName: String, val deviceName: String,
        val qualityBars: Int = 0, val hopCount: Int = 1) {
        val displayName: String get() = riderName.ifBlank { deviceName.ifBlank { "Rider" } }
    }
    data class Diagnostics(val directPeers: Int, val receivedPackets: Int, val relayedPackets: Int,
        val maxObservedHops: Int, val advertisingActive: Boolean, val discoveryActive: Boolean,
        val discoveredEndpoints: Int, val connectionAttempts: Int, val successfulConnections: Int,
        val failedConnections: Int, val pendingRequests: Int, val sendFailures: Int,
        val lastError: String, val profile: String, val reachableRiders: Int = 0, val droppedAudio: Long = 0)
    interface Listener {
        fun onLog(message: String)
        fun onDirectPeerCount(count: Int)
        fun onAudioPacket(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray)
    }
    var internetPeers: () -> Set<String> = { emptySet() }
    var internetSend: (String, ByteArray) -> Boolean = { _, _ -> false }
    fun receiveInternet(peer: String, bytes: ByteArray) { controller?.receiveInternet(peer, bytes) }
    fun bridgeSummary() = controller?.bridgeSummary().orEmpty()
    @Volatile private var controller: OfflineMeshController? = null
    fun start(riderName: String, rideCode: String, labRole: LabRole = LabRole.NORMAL,
              deviceName: String = "", preferOffline: Boolean = false, sharedNodeId: java.util.UUID? = null) {
        stop()
        val next = OfflineMeshController(context,
            onLog = { listener.onLog(it); listener.onDirectPeerCount(controller?.connectedPeerCount() ?: 0) },
            onAudioFrame = listener::onAudioPacket, internetPeers = internetPeers, internetSend = internetSend)
        controller = next
        next.start(riderName, rideCode, deviceName, labRole.ordinal, sharedNodeId)
    }
    fun stop() { controller?.stop(); controller = null; listener.onDirectPeerCount(0) }
    fun sendLocalAudio(pcm: ByteArray) { controller?.sendAudioFrame(pcm) }
    fun decodeForPlayout(source: String, packet: ByteArray?): ByteArray? = controller?.decodeForPlayout(source, packet)
    fun refreshDiscovery(reason: String) { controller?.refreshDiscovery(reason) }
    fun endpointIdForSource(sourceId: String): String? = sourceId
    fun directPeers(): List<RiderPeer> = controller?.connectedPeerDetails()?.map {
        RiderPeer(it.nodeId, it.riderName, it.deviceName)
    }.orEmpty()
    fun reachablePeers(): List<RiderPeer> = controller?.reachablePeerDetails()?.map {
        RiderPeer(it.nodeId, it.riderName, it.deviceName, hopCount = it.hops)
    }.orEmpty()
    fun diagnostics(): Diagnostics {
        val c = controller
        val t = c?.transportStats()
        return Diagnostics(c?.connectedPeerCount() ?: 0, (c?.audioRxCount() ?: 0).toInt(),
            (c?.relayCount() ?: 0).toInt(), c?.maximumHops() ?: 0,
            t?.advertising ?: false, t?.discovering ?: false, t?.found ?: 0,
            t?.attempts ?: 0, t?.connected ?: 0, t?.failed ?: 0, t?.pending ?: 0,
            t?.sendFailed ?: 0, c?.diagnosticSummary().orEmpty(), "OFFLINE OPUS • EIGHT-RIDER TEST",
            if (c?.isActive() == true) c.reachablePeerDetails().size + 1 else 0, c?.audioDropCount() ?: 0)
    }
}
