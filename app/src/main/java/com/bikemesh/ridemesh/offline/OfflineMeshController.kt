package com.bikemesh.ridemesh.offline

import android.content.Context
import com.bikemesh.ridemesh.transport.WifiAwareWireProtocol
import java.util.UUID

/** Dedicated Android offline coordinator. Existing online mesh and Maps stay untouched. */
class OfflineMeshController(
    context: Context,
    private val onLog: (String) -> Unit,
) : NearbyClusterTransport.Listener {

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("ridemesh_offline_mesh", Context.MODE_PRIVATE)

    @Volatile private var cluster: NearbyClusterTransport? = null
    @Volatile private var lastPeerName: String? = null
    @Volatile private var lastRttMs: Int? = null
    @Volatile private var lastNearbyStatus: String = "NEARBY DIAG • NOT STARTED"

    fun start(riderName: String, rideCode: String) {
        stop()
        val normalizedCode = rideCode.trim().uppercase()
        if (normalizedCode.isBlank()) {
            lastNearbyStatus = "NEARBY DIAG • INVALID RIDE CODE"
            onLog("OFFLINE MESH • enter or scan a ride code first")
            return
        }
        val nodeId = prefs.getString(KEY_NODE_ID, null)
            ?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString().also { prefs.edit().putString(KEY_NODE_ID, it).apply() }

        val token = WifiAwareWireProtocol.rideToken(normalizedCode)
        lastPeerName = null
        lastRttMs = null
        lastNearbyStatus = "NEARBY DIAG • START REQUESTED"
        cluster = NearbyClusterTransport(
            context = appContext,
            nodeId = nodeId,
            riderName = riderName.ifBlank { "Rider" },
            rideToken = token,
            listener = this,
        ).also { it.start() }

        onLog("OFFLINE MESH ACTIVE • same-code Nearby P2P_CLUSTER • hotspot disabled")
    }

    fun stop() {
        cluster?.stop()
        cluster = null
        lastPeerName = null
        lastRttMs = null
        lastNearbyStatus = "NEARBY DIAG • STOPPED"
    }

    fun isActive(): Boolean = cluster != null
    fun hotspotInvitePayload(): String? = null
    fun hotspotCredentialsSummary(): String? = null
    fun connectedPeerCount(): Int = cluster?.connectedPeerCount() ?: 0
    fun connectedPeerName(): String? = lastPeerName ?: cluster?.firstPeerName()
    fun currentRttMs(): Int? = lastRttMs
    fun diagnosticSummary(): String = lastNearbyStatus.removePrefix("NEARBY DIAG • ")

    fun sendDiagnosticEnvelope(text: String): Boolean =
        cluster?.send(text.toByteArray(Charsets.UTF_8)) == true

    override fun onStatus(message: String) {
        lastNearbyStatus = message
        onLog(message)
    }

    override fun onPeerConnected(nodeId: String, riderName: String) {
        lastPeerName = riderName.ifBlank { "Android rider" }
        lastNearbyStatus = "NEARBY DIAG • IDENTITY OK • $lastPeerName"
        onLog("OFFLINE ANDROID↔ANDROID CONNECTED • $lastPeerName")
        cluster?.send("RIDEMESH_OFFLINE_LINK_OK".toByteArray(Charsets.UTF_8))
    }

    override fun onPeerDisconnected(nodeId: String) {
        lastPeerName = null
        lastRttMs = null
        lastNearbyStatus = "NEARBY DIAG • PEER LOST • REDISCOVERING"
        onLog("OFFLINE PEER LOST • automatic discovery/reconnect remains active")
    }

    override fun onRtt(nodeId: String, rttMs: Int) {
        val previousBucket = lastRttMs?.div(10)
        lastRttMs = rttMs
        if (previousBucket != rttMs.div(10)) {
            onLog("OFFLINE LINK • ${lastPeerName ?: "peer"} • ${rttMs}ms RTT")
        }
    }

    override fun onData(nodeId: String, payload: ByteArray) {
        val preview = payload.toString(Charsets.UTF_8).take(80)
        onLog("Offline packet from ${lastPeerName ?: nodeId.take(8)}: $preview")
    }

    companion object { private const val KEY_NODE_ID = "node_id" }
}
