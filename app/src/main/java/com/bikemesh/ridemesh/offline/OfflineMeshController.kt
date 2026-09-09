package com.bikemesh.ridemesh.offline

import android.content.Context
import java.util.UUID

/**
 * Cross-platform offline coordinator for the dedicated test build.
 *
 * The first reliable Android <-> iPhone path is Android LocalOnlyHotspot +
 * Bonjour + TCP. Wi-Fi Aware remains in the codebase for later capability-based
 * use, but this controller intentionally does not start it so both transports do
 * not compete for TCP 49355 during the proof-of-connectivity test.
 */
class OfflineMeshController(
    context: Context,
    private val onLog: (String) -> Unit,
) : LocalHotspotHost.Listener {

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("ridemesh_offline_mesh", Context.MODE_PRIVATE)

    @Volatile
    private var host: LocalHotspotHost? = null

    @Volatile
    private var invitePayload: String? = null

    @Volatile
    private var hotspotSummary: String? = null

    @Volatile
    private var lastPeerName: String? = null

    @Volatile
    private var lastRttMs: Int? = null

    fun start(riderName: String, rideCode: String) {
        stop()
        val nodeId = prefs.getString(KEY_NODE_ID, null)
            ?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString().also {
                prefs.edit().putString(KEY_NODE_ID, it).apply()
            }

        invitePayload = null
        hotspotSummary = null
        lastPeerName = null
        lastRttMs = null

        host = LocalHotspotHost(
            context = appContext,
            nodeId = nodeId,
            riderName = riderName,
            rideCode = rideCode,
            listener = this,
        ).also { it.start() }

        onLog("Offline cross-platform link starting • Android hotspot + Bonjour + TCP")
    }

    fun stop() {
        host?.stop()
        host = null
        invitePayload = null
        hotspotSummary = null
        lastPeerName = null
        lastRttMs = null
    }

    fun hotspotInvitePayload(): String? = invitePayload

    fun hotspotCredentialsSummary(): String? = hotspotSummary

    fun connectedPeerCount(): Int = host?.connectedPeerCount() ?: 0

    fun connectedPeerName(): String? = lastPeerName

    fun currentRttMs(): Int? = lastRttMs

    fun sendDiagnosticEnvelope(text: String): Boolean =
        host?.send(text.toByteArray(Charsets.UTF_8)) == true

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
        onLog("OFFLINE LINK READY • tap INVITE → SHOW QR on Android, then scan it on iPhone")
    }

    override fun onPeerConnected(nodeId: String, riderName: String) {
        lastPeerName = riderName.ifBlank { "iPhone rider" }
        onLog("OFFLINE PEER CONNECTED • ${lastPeerName}")
        host?.send("RIDEMESH_OFFLINE_LINK_OK".toByteArray(Charsets.UTF_8), nodeId)
    }

    override fun onPeerDisconnected(nodeId: String) {
        lastPeerName = null
        lastRttMs = null
        onLog("OFFLINE PEER LOST • waiting for reconnect")
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
