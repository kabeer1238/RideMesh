package com.bikemesh.ridemesh.offline

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import com.bikemesh.ridemesh.transport.WifiAwareWireProtocol
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/** September 11 Opus/router/transport integration, extended for eight-rider hybrid field tests.
 * The receive callback carries encoded Opus to AudioEngine for reorder-before-decode.
 */
class OfflineMeshController(
    context: Context,
    private val onLog: (String) -> Unit,
    private val onAudioFrame: (String, Int, Long, ByteArray) -> Unit = { _, _, _, _ -> },
    private val internetPeers: () -> Set<String> = { emptySet() },
    private val internetSend: (String, ByteArray) -> Boolean = { _, _ -> false },
) : NearbyClusterTransport.Listener {
    data class PeerDetails(val nodeId: String, val riderName: String, val deviceName: String, val rttMs: Int?)
    data class ReachablePeer(val nodeId: String, val riderName: String, val deviceName: String, val hops: Int)
    private data class Presence(val peer: ReachablePeer, val at: Long)
    private val appContext = context.applicationContext
    private val opus = OpusVoiceCodec()
    private val handler = Handler(Looper.getMainLooper())
    private val roster = ConcurrentHashMap<String, Presence>()
    private val rtt = ConcurrentHashMap<String, Int>()
    private val tx = AtomicLong()
    private val rx = AtomicLong()
    private val dropped = AtomicLong()
    private val maxHops = AtomicInteger()
    @Volatile private var cluster: NearbyClusterTransport? = null
    @Volatile private var router: MeshRelayRouter? = null
    @Volatile private var localNodeId: UUID? = null
    @Volatile private var status = "STOPPED"
    private var presencePayload = ByteArray(0)
    private var presenceName = ""
    private var presenceDevice = ""
    private var election: GatewayElection? = null
    private val internetTx = AtomicLong()
    fun bridgeSummary(): String = "Internet links: ${internetPeers().size} • uplink packets: ${internetTx.get()}"
    private fun announce() {
        presencePayload = JSONObject().put("name", presenceName).put("device", presenceDevice)
            .put("gateways", org.json.JSONArray(internetPeers().toList())).toString().toByteArray()
        router?.originatePresence(presencePayload)
    }
    fun receiveInternet(peer: String, bytes: ByteArray) {
        val packet = RideMeshEnvelope.decode(bytes) ?: return
        if (packet.internetHops != 1 || peer !in internetPeers()) return
        router?.receive(peer, bytes)
    }
    private val heartbeat = object : Runnable {
        override fun run() {
            if (!isActive()) return
            announce()
            val now = SystemClock.elapsedRealtime()
            roster.entries.removeAll { now - it.value.at > 8000 }
            handler.postDelayed(this, 2000)
        }
    }
    fun start(riderName: String, rideCode: String, deviceName: String = "Android device", labRole: Int = 0, sharedNodeId: UUID? = null) {
        stop()
        val code = rideCode.trim().uppercase()
        require(code.matches(Regex("[A-Z0-9]{5,12}"))) { "Invalid ride code" }
        // Per-ride identity prevents a sequence reset being mistaken for stale audio on peers.
        val node = sharedNodeId ?: UUID.randomUUID()
        election = GatewayElection(node.toString(), SystemClock::elapsedRealtime)
        presenceName = riderName.take(24)
        presenceDevice = deviceName.take(48)
        localNodeId = node
        presencePayload = JSONObject().put("name", riderName.take(24)).put("device", deviceName.take(48))
            .toString().toByteArray(Charsets.UTF_8)
        val transport = NearbyClusterTransport(appContext, node.toString(), riderName,
            WifiAwareWireProtocol.rideToken(code), deviceName, this, labRole)
        cluster = transport
        router = MeshRelayRouter(node,
            sendToNeighborsExcept = { exclude, bytes -> transport.sendExceptNode(exclude, bytes) },
            onDeliver = { envelope ->
                if (envelope.originNodeId != node && isActive()) {
                    val source = envelope.originNodeId.toString()
                    val hops = envelope.hopCount + 1
                    maxHops.updateAndGet { maxOf(it, hops) }
                    when (envelope.type) {
                        RideMeshEnvelope.Type.AUDIO -> {
                            if (envelope.payload.size in 8..263) {
                                rx.incrementAndGet()
                                onAudioFrame(source, envelope.sequence, envelope.createdAtMs, envelope.payload)
                            } else dropped.incrementAndGet()
                        }
                        RideMeshEnvelope.Type.PRESENCE -> runCatching {
                            val json = JSONObject(String(envelope.payload, Charsets.UTF_8))
                            if (envelope.internetHops == 0) {
                                val array = json.optJSONArray("gateways")
                                val destinations = (0 until minOf(array?.length() ?: 0, 7)).mapNotNull {
                                    runCatching { UUID.fromString(array!!.getString(it)).toString() }.getOrNull()
                                }.toSet()
                                election?.observe(source, destinations)
                            }
                            if (roster.size < 7 || roster.containsKey(source)) {
                                roster[source] = Presence(ReachablePeer(source, json.optString("name", "Rider").take(24),
                                    json.optString("device", "Android device").take(48), hops), SystemClock.elapsedRealtime())
                            }
                        }.let { Unit }
                        RideMeshEnvelope.Type.DIAGNOSTIC -> onLog("ROUTE PROBE • $hops links • ${source.take(8)}")
                        else -> Unit
                    }
                }
            }, onStatus = onLog, sendToInternet = { envelope ->
                var sent = false
                for (peer in internetPeers()) {
                    if (peer == envelope.originNodeId.toString()) continue
                    // Own audio/presence always takes its direct internet path. Relays
                    // elect separately for each reachable internet destination.
                    if (envelope.originNodeId == node || election?.selected(peer) == node.toString()) {
                        if (internetSend(peer, envelope.encode())) { internetTx.incrementAndGet(); sent = true }
                    }
                }
                sent
            })
        transport.start()
        handler.post(heartbeat)
        onLog("OFFLINE OPUS • 16 kHz • 20 ms • 32 kbps target • eight-rider hybrid test")
    }
    fun stop() {
        handler.removeCallbacks(heartbeat)
        cluster?.stop(); cluster = null; router = null; localNodeId = null
        roster.clear(); rtt.clear(); tx.set(0); rx.set(0); dropped.set(0); maxHops.set(0)
        opus.reset(); election = null; internetTx.set(0); status = "STOPPED"
    }
    fun isActive() = cluster != null
    fun connectedPeerCount() = cluster?.connectedPeerCount() ?: 0
    fun connectedPeerDetails() = cluster?.peerSnapshots()?.map {
        PeerDetails(it.nodeId, it.riderName, it.deviceName, rtt[it.nodeId])
    }.orEmpty()
    fun reachablePeerDetails() = roster.values.map { it.peer }.sortedBy { it.riderName.lowercase() }
    fun connectedPeerName() = cluster?.firstPeerName()
    fun currentRttMs(): Int? = rtt.values.firstOrNull()
    fun diagnosticSummary() = status
    fun audioTxCount() = tx.get()
    fun audioRxCount() = rx.get()
    fun audioDropCount() = dropped.get() + (cluster?.realtimeAudioDropped() ?: 0)
    fun relayCount() = router?.relayCount() ?: 0L
    fun maximumHops() = maxHops.get()
    fun transportStats() = cluster?.stats()
    fun hotspotInvitePayload(): String? = null
    fun hotspotCredentialsSummary(): String? = null
    fun refreshDiscovery(reason: String) { cluster?.refreshDiscovery(reason) }
    fun sendDiagnosticEnvelope(text: String) = router?.originateDiagnostic(text) == true
    fun sendAudioFrame(audio: ByteArray): Boolean {
        if (!isActive() || connectedPeerCount() == 0 && internetPeers().isEmpty()) return false
        val packet = opus.encode20ms(audio) ?: run { dropped.incrementAndGet(); return false }
        val sent = router?.originateAudio(packet) == true
        if (sent) tx.incrementAndGet() else dropped.incrementAndGet()
        return sent
    }
    fun decodeForPlayout(source: String, packet: ByteArray?): ByteArray? {
        val pcm = if (packet == null) opus.conceal20ms(source) else opus.decode20ms(source, packet)
        if (pcm == null) dropped.incrementAndGet()
        return pcm
    }
    override fun onStatus(message: String) { status = message; onLog(message) }
    override fun onPeerConnected(nodeId: String, riderName: String) {
        announce()
        router?.originateDiagnostic("SIX_RIDER_PROBE")
        onLog("OFFLINE CONNECTED • $riderName")
    }
    override fun onPeerDisconnected(nodeId: String) {
        rtt.remove(nodeId)
        // Indirect identities expire through presence; another path may still reach them.
        onLog("OFFLINE LINK LOST • rediscovery active")
    }
    override fun onRtt(nodeId: String, rttMs: Int) { rtt[nodeId] = rttMs }
    override fun onData(nodeId: String, payload: ByteArray) { router?.receive(nodeId, payload) }
}
