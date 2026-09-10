package com.bikemesh.ridemesh.offline

import android.content.Context
import android.os.SystemClock
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

    data class PeerDetails(val nodeId: String, val riderName: String, val deviceName: String, val rttMs: Int?)

    private val appContext = context.applicationContext
    private val prefs = appContext.getSharedPreferences("ridemesh_offline_mesh", Context.MODE_PRIVATE)
    private val opus = OpusVoiceCodec()

    @Volatile private var cluster: NearbyClusterTransport? = null
    @Volatile private var router: MeshRelayRouter? = null
    @Volatile private var localNodeId: UUID? = null
    @Volatile private var lastPeerName: String? = null
    @Volatile private var lastRttMs: Int? = null
    @Volatile private var lastNearbyStatus: String = "NEARBY DIAG • NOT STARTED"

    private val peerRttMs = ConcurrentHashMap<String, Int>()
    private val txAudioFrames = AtomicLong(0)
    private val rxAudioFrames = AtomicLong(0)
    private val codecDroppedFrames = AtomicLong(0)
    private val lateAudioFrames = AtomicLong(0)
    private val lastAudioSequence = ConcurrentHashMap<String, Int>()
    private val audioClockOffsetMs = ConcurrentHashMap<String, Long>()

    fun start(riderName: String, rideCode: String, deviceName: String = "Android device") {
        stop()
        val normalizedCode = rideCode.trim().uppercase()
        if (normalizedCode.isBlank()) { lastNearbyStatus = "NEARBY DIAG • INVALID RIDE CODE"; onLog("OFFLINE MESH • enter or scan a ride code first"); return }
        val nodeIdText = prefs.getString(KEY_NODE_ID, null)?.takeIf { it.isNotBlank() }
            ?: UUID.randomUUID().toString().also { prefs.edit().putString(KEY_NODE_ID, it).apply() }
        val nodeId = runCatching { UUID.fromString(nodeIdText) }.getOrElse { UUID.randomUUID().also { replacement -> prefs.edit().putString(KEY_NODE_ID, replacement.toString()).apply() } }
        localNodeId = nodeId
        val token = WifiAwareWireProtocol.rideToken(normalizedCode)
        lastPeerName = null; lastRttMs = null; peerRttMs.clear(); txAudioFrames.set(0); rxAudioFrames.set(0); codecDroppedFrames.set(0); lateAudioFrames.set(0); lastAudioSequence.clear(); audioClockOffsetMs.clear(); opus.reset()
        lastNearbyStatus = "NEARBY DIAG • START REQUESTED"

        val newCluster = NearbyClusterTransport(appContext, nodeId.toString(), riderName.ifBlank { "Rider" }, token, deviceName.ifBlank { "Android device" }, this)
        cluster = newCluster
        router = MeshRelayRouter(
            localNodeId = nodeId,
            sendToNeighborsExcept = { excludedNode, payload -> newCluster.sendExceptNode(excludedNode, payload) },
            onDeliver = { envelope ->
                when (envelope.type) {
                    RideMeshEnvelope.Type.AUDIO -> if (envelope.originNodeId != nodeId) {
                        val sourceId = envelope.originNodeId.toString()
                        val previous = lastAudioSequence[sourceId]
                        if (previous != null && !isNewerSequence(envelope.sequence, previous)) {
                            lateAudioFrames.incrementAndGet()
                        } else {
                            val now = System.currentTimeMillis()
                            val observedOffset = now - envelope.createdAtMs
                            val baseline = audioClockOffsetMs.merge(sourceId, observedOffset) { old, value -> minOf(old, value) } ?: observedOffset
                            val excessAgeMs = observedOffset - baseline
                            if (excessAgeMs > MAX_AUDIO_EXCESS_AGE_MS) {
                                lateAudioFrames.incrementAndGet()
                                lastAudioSequence[sourceId] = envelope.sequence
                            } else {
                                val pcm = opus.decode20ms(sourceId, envelope.payload)
                                if (pcm != null) {
                                    lastAudioSequence[sourceId] = envelope.sequence
                                    rxAudioFrames.incrementAndGet()
                                    onAudioFrame(sourceId, envelope.sequence, envelope.createdAtMs, pcm)
                                } else codecDroppedFrames.incrementAndGet()
                            }
                        }
                    }
                    RideMeshEnvelope.Type.DIAGNOSTIC -> onLog("MESH ENVELOPE • hop=${envelope.hopCount} ttl=${envelope.ttl} • ${envelope.payload.toString(Charsets.UTF_8).take(80)}")
                    else -> onLog("MESH ENVELOPE • ${envelope.type} • hop=${envelope.hopCount} ttl=${envelope.ttl}")
                }
            }, onStatus = onLog)
        newCluster.start()
        onLog("OFFLINE MESH ACTIVE • same-code Nearby P2P_CLUSTER • hotspot disabled")
        onLog("VOICE OPUS LOW-LATENCY • 20ms • stale>${MAX_AUDIO_EXCESS_AGE_MS}ms DROP • newest-frame-wins")
    }

    fun stop() { cluster?.stop(); cluster=null; router=null; localNodeId=null; lastPeerName=null; lastRttMs=null; peerRttMs.clear(); txAudioFrames.set(0); rxAudioFrames.set(0); codecDroppedFrames.set(0); lateAudioFrames.set(0); lastAudioSequence.clear(); audioClockOffsetMs.clear(); opus.reset(); lastNearbyStatus="NEARBY DIAG • STOPPED" }
    fun isActive()=cluster!=null
    fun hotspotInvitePayload():String?=null
    fun hotspotCredentialsSummary():String?=null
    fun connectedPeerCount()=cluster?.connectedPeerCount()?:0
    fun connectedPeerName():String?=lastPeerName?:cluster?.firstPeerName()
    fun currentRttMs():Int?=lastRttMs
    fun diagnosticSummary()=lastNearbyStatus.removePrefix("NEARBY DIAG • ")
    fun audioTxCount()=txAudioFrames.get()
    fun audioRxCount()=rxAudioFrames.get()
    fun audioDropCount()=codecDroppedFrames.get()+lateAudioFrames.get()+(cluster?.realtimeAudioDropped()?:0L)
    fun connectedPeerDetails():List<PeerDetails> = cluster?.peerSnapshots()?.map { PeerDetails(it.nodeId,it.riderName,it.deviceName,peerRttMs[it.nodeId]) }?: emptyList()
    fun sendDiagnosticEnvelope(text:String)=router?.originateDiagnostic(text)==true

    fun sendAudioFrame(audio:ByteArray):Boolean {
        if(audio.size!=OpusVoiceCodec.PCM_FRAME_BYTES)return false
        val packet=opus.encode20ms(audio)?:run{codecDroppedFrames.incrementAndGet();return false}
        val sent=router?.originateAudio(packet)==true
        if(sent)txAudioFrames.incrementAndGet() else codecDroppedFrames.incrementAndGet()
        return sent
    }

    override fun onStatus(message:String){lastNearbyStatus=message;onLog(message)}
    override fun onPeerConnected(nodeId:String,riderName:String){lastPeerName=riderName.ifBlank{"Android rider"};lastNearbyStatus="NEARBY DIAG • IDENTITY OK • $lastPeerName";onLog("OFFLINE ANDROID↔ANDROID CONNECTED • $lastPeerName");router?.originateDiagnostic("RIDEMESH_ROUTE_PROBE:${localNodeId.toString().take(8)}")}
    override fun onPeerDisconnected(nodeId:String){peerRttMs.remove(nodeId);opus.forgetPeer(nodeId);lastAudioSequence.remove(nodeId);audioClockOffsetMs.remove(nodeId);val peers=cluster?.peerSnapshots().orEmpty();lastPeerName=peers.firstOrNull()?.riderName;lastRttMs=peers.firstOrNull()?.nodeId?.let(peerRttMs::get);lastNearbyStatus="NEARBY DIAG • PEER LOST • REDISCOVERING";onLog("OFFLINE PEER LOST • automatic discovery/reconnect remains active")}
    override fun onRtt(nodeId:String,rttMs:Int){val previousBucket=peerRttMs[nodeId]?.div(10);peerRttMs[nodeId]=rttMs;lastRttMs=rttMs;if(previousBucket!=rttMs.div(10)){val name=connectedPeerDetails().firstOrNull{it.nodeId==nodeId}?.riderName?:lastPeerName?:"peer";onLog("OFFLINE LINK • $name • ${rttMs}ms RTT • OPUS LOW-LATENCY")}}
    override fun onData(nodeId:String,payload:ByteArray){router?.receive(nodeId,payload)?:onLog("ROUTER DROP • router unavailable")}

    private fun isNewerSequence(sequence:Int,previous:Int):Boolean = sequence>previous || (previous>Int.MAX_VALUE-10000 && sequence<10000)

    companion object { private const val KEY_NODE_ID="node_id"; private const val MAX_AUDIO_EXCESS_AGE_MS=140L }
}
