package com.bikemesh.ridemesh.offline

import android.content.Context
import com.bikemesh.ridemesh.transport.WifiAwareWireProtocol
import java.util.UUID

/**
 * Offline coordinator for the dedicated Android test build.
 *
 * All Android riders initially start a LocalOnlyHotspot and BLE scan. Same-code
 * advertisements include a deterministic per-install rank; the higher-ranked
 * device remains host while the lower-ranked device automatically yields,
 * securely reads the host invitation, asks Android to join that local Wi-Fi,
 * discovers _ridemesh._tcp and completes the RMESH1 handshake.
 */
class OfflineMeshController(
    context: Context,
    private val onLog: (String) -> Unit,
) : LocalHotspotHost.Listener, AndroidHotspotClient.Listener {

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("ridemesh_offline_mesh", Context.MODE_PRIVATE)

    @Volatile private var host: LocalHotspotHost? = null
    @Volatile private var scanner: NearbyHotspotClient? = null
    @Volatile private var client: AndroidHotspotClient? = null
    @Volatile private var invitePayload: String? = null
    @Volatile private var hotspotSummary: String? = null
    @Volatile private var lastPeerName: String? = null
    @Volatile private var lastRttMs: Int? = null
    @Volatile private var clientConnected = false
    @Volatile private var currentNodeId: String? = null
    @Volatile private var currentRiderName: String = "Rider"
    @Volatile private var currentRideCode: String = ""

    fun start(riderName: String, rideCode: String) {
        stop()
        val nodeId = prefs.getString(KEY_NODE_ID, null)
            ?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString().also {
                prefs.edit().putString(KEY_NODE_ID, it).apply()
            }

        currentNodeId = nodeId
        currentRiderName = riderName.ifBlank { "Rider" }
        currentRideCode = rideCode.trim().uppercase()
        invitePayload = null
        hotspotSummary = null
        lastPeerName = null
        lastRttMs = null
        clientConnected = false

        host = LocalHotspotHost(
            context = appContext,
            nodeId = nodeId,
            riderName = currentRiderName,
            rideCode = currentRideCode,
            listener = this,
        ).also { it.start() }

        scanner = NearbyHotspotClient(
            context = appContext,
            rideToken = WifiAwareWireProtocol.rideToken(currentRideCode),
            onStatus = onLog,
            onInvite = ::becomeAndroidClient,
        ).also { it.start() }

        onLog("Offline Android link starting • same-code BLE election + direct Wi-Fi + RMESH1")
    }

    fun stop() {
        scanner?.stop()
        scanner = null
        client?.stop()
        client = null
        host?.stop()
        host = null
        invitePayload = null
        hotspotSummary = null
        lastPeerName = null
        lastRttMs = null
        clientConnected = false
    }

    fun hotspotInvitePayload(): String? = invitePayload
    fun hotspotCredentialsSummary(): String? = hotspotSummary
    fun connectedPeerCount(): Int = if (clientConnected) 1 else (host?.connectedPeerCount() ?: 0)
    fun connectedPeerName(): String? = lastPeerName
    fun currentRttMs(): Int? = lastRttMs

    fun sendDiagnosticEnvelope(text: String): Boolean {
        val data = text.toByteArray(Charsets.UTF_8)
        return client?.send(data) == true || host?.send(data) == true
    }

    private fun becomeAndroidClient(payload: String) {
        val nodeId = currentNodeId ?: return
        if (client != null) return
        onLog("OFFLINE ROLE ELECTED • this device is CLIENT")

        // Stop our own temporary hotspot before Android requests the winner's
        // LocalOnlyHotspot. The higher-ranked peer keeps advertising/hosting.
        host?.stop()
        host = null
        invitePayload = null
        hotspotSummary = null

        client = AndroidHotspotClient(
            context = appContext,
            nodeId = nodeId,
            riderName = currentRiderName,
            rideCode = currentRideCode,
            listener = this,
        ).also { it.start(payload) }
    }

    override fun onStatus(message: String) {
        onLog(message)
    }

    override fun onHotspotReady(ssid: String, passphrase: String?, invitePayload: String) {
        this.invitePayload = invitePayload
        this.hotspotSummary = if (passphrase.isNullOrBlank()) {
            "SSID: $ssid • OPEN"
        } else {
            "SSID: $ssid • Password: $passphrase"
        }
        onLog("OFFLINE HOST READY • waiting for same-code Android rider")
    }

    override fun onPeerConnected(nodeId: String, riderName: String) {
        lastPeerName = riderName.ifBlank { "Android rider" }
        clientConnected = false
        onLog("OFFLINE PEER CONNECTED • $lastPeerName")
        host?.send("RIDEMESH_OFFLINE_LINK_OK".toByteArray(Charsets.UTF_8), nodeId)
    }

    override fun onPeerDisconnected(nodeId: String) {
        lastPeerName = null
        lastRttMs = null
        onLog("OFFLINE PEER LOST • waiting for reconnect")
    }

    override fun onConnected(nodeId: String, riderName: String) {
        clientConnected = true
        lastPeerName = riderName.ifBlank { "Android rider" }
        onLog("OFFLINE ANDROID↔ANDROID CONNECTED • $lastPeerName")
        client?.send("RIDEMESH_OFFLINE_LINK_OK".toByteArray(Charsets.UTF_8))
    }

    override fun onDisconnected(nodeId: String?) {
        clientConnected = false
        lastPeerName = null
        lastRttMs = null
        onLog("OFFLINE ANDROID CLIENT LOST • restart ride to reconnect")
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

    companion object {
        private const val KEY_NODE_ID = "node_id"
    }
}
