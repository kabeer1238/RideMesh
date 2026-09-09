package com.bikemesh.ridemesh.offline

import android.content.Context
import com.bikemesh.ridemesh.transport.RideMeshTransport
import com.bikemesh.ridemesh.transport.TransportMetrics
import com.bikemesh.ridemesh.transport.TransportState
import com.bikemesh.ridemesh.transport.WifiAwareTransport
import java.util.UUID

/**
 * Phase-1 coordinator used by the Android app while the full routing layer is
 * being integrated. It starts Wi-Fi Aware for the active ride and exposes clear
 * diagnostics without changing the existing production Internet/Nearby voice
 * pipeline.
 */
class OfflineMeshController(
    context: Context,
    private val onLog: (String) -> Unit,
) : RideMeshTransport.Listener {

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("ridemesh_offline_mesh", Context.MODE_PRIVATE)

    @Volatile
    private var transport: WifiAwareTransport? = null

    private var lastPeerCount = -1
    private var lastRttBucket: Int? = null

    fun start(riderName: String, rideCode: String) {
        stop()
        val nodeId = prefs.getString(KEY_NODE_ID, null)
            ?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString().also {
                prefs.edit().putString(KEY_NODE_ID, it).apply()
            }

        lastPeerCount = -1
        lastRttBucket = null
        transport = WifiAwareTransport(
            context = appContext,
            nodeId = nodeId,
            riderName = riderName,
            rideCode = rideCode,
        ).also {
            it.setListener(this)
            it.start()
        }
        onLog("Offline mesh v1 starting • Wi-Fi Aware Android↔iPhone protocol")
    }

    fun stop() {
        transport?.setListener(null)
        transport?.stop()
        transport = null
        lastPeerCount = -1
        lastRttBucket = null
    }

    fun sendDiagnosticEnvelope(text: String): Boolean =
        transport?.send(text.toByteArray(Charsets.UTF_8)) == true

    override fun onEnvelopeReceived(
        transport: RideMeshTransport,
        fromPeerId: String?,
        envelope: ByteArray,
    ) {
        val preview = envelope.toString(Charsets.UTF_8).take(80)
        onLog("Offline packet from ${fromPeerId?.take(8) ?: "peer"}: $preview")
    }

    override fun onStateChanged(transport: RideMeshTransport, state: TransportState) {
        val label = when (state) {
            TransportState.STOPPED -> "stopped"
            TransportState.STARTING -> "starting"
            TransportState.AVAILABLE -> "available"
            TransportState.DEGRADED -> "degraded"
            TransportState.UNAVAILABLE -> "unavailable on this phone / permission missing"
        }
        onLog("Offline Wi-Fi Aware: $label")
    }

    override fun onMetricsChanged(transport: RideMeshTransport, metrics: TransportMetrics) {
        val rttBucket = metrics.estimatedRttMs?.div(10)?.times(10)
        if (metrics.reachablePeers == lastPeerCount && rttBucket == lastRttBucket) return
        lastPeerCount = metrics.reachablePeers
        lastRttBucket = rttBucket
        val rttText = metrics.estimatedRttMs?.let { " • ${it}ms RTT" }.orEmpty()
        onLog("Offline peers: ${metrics.reachablePeers}$rttText")
    }

    companion object {
        private const val KEY_NODE_ID = "node_id"
    }
}
