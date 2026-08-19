package com.bikemesh.ridemesh.mesh

import android.content.Context
import com.google.android.gms.nearby.Nearby
import com.google.android.gms.nearby.connection.AdvertisingOptions
import com.google.android.gms.nearby.connection.ConnectionInfo
import com.google.android.gms.nearby.connection.ConnectionLifecycleCallback
import com.google.android.gms.nearby.connection.ConnectionOptions
import com.google.android.gms.nearby.connection.ConnectionResolution
import com.google.android.gms.nearby.connection.ConnectionType
import com.google.android.gms.nearby.connection.ConnectionsClient
import com.google.android.gms.nearby.connection.DiscoveredEndpointInfo
import com.google.android.gms.nearby.connection.DiscoveryOptions
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback
import com.google.android.gms.nearby.connection.Payload
import com.google.android.gms.nearby.connection.PayloadCallback
import com.google.android.gms.nearby.connection.PayloadTransferUpdate
import com.google.android.gms.nearby.connection.Strategy
import java.util.Collections
import java.util.LinkedHashMap
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Local RideMesh transport.
 *
 * Nearby Connections P2P_CLUSTER supplies multiple direct nearby links.
 * RideMesh adds packet IDs + TTL broadcast forwarding for multi-hop relay.
 * NON_DISRUPTIVE connection mode is intentional: local mesh should coexist
 * with mobile/Wi-Fi Internet so the hybrid router can hand over cleanly.
 */
class MeshNode(
    context: Context,
    private val listener: Listener,
) {
    enum class LabRole { NORMAL, A, B, C }

    data class Diagnostics(
        val directPeers: Int,
        val receivedPackets: Int,
        val relayedPackets: Int,
        val maxObservedHops: Int,
        val advertisingActive: Boolean,
        val discoveryActive: Boolean,
        val discoveredEndpoints: Int,
        val connectionAttempts: Int,
        val successfulConnections: Int,
        val failedConnections: Int,
        val pendingRequests: Int,
        val sendFailures: Int,
        val lastError: String,
        val profile: String,
    )

    data class RiderPeer(
        val endpointId: String,
        val riderName: String,
        val deviceName: String,
        val qualityBars: Int = 4,
    ) {
        val displayName: String
            get() = riderName.ifBlank { deviceName.ifBlank { "Rider" } }
    }

    interface Listener {
        fun onLog(message: String)
        fun onDirectPeerCount(count: Int)
        fun onAudioPacket(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray)
    }

    private val client: ConnectionsClient = Nearby.getConnectionsClient(context)
    private val nodeId = UUID.randomUUID()
    private val sequence = AtomicInteger(0)
    private val receivedPackets = AtomicInteger(0)
    private val relayedPackets = AtomicInteger(0)
    private val maxObservedHops = AtomicInteger(0)
    private val discoveredEndpoints = AtomicInteger(0)
    private val connectionAttempts = AtomicInteger(0)
    private val successfulConnections = AtomicInteger(0)
    private val failedConnections = AtomicInteger(0)
    private val sendFailures = AtomicInteger(0)
    private val refreshScheduled = AtomicBoolean(false)
    private val connected = ConcurrentHashMap.newKeySet<String>()
    private val requested = ConcurrentHashMap.newKeySet<String>()
    private val endpointNames = ConcurrentHashMap<String, String>()
    private val originEndpoints = ConcurrentHashMap<UUID, String>()

    private var riderName: String = "Rider"
    private var deviceName: String = "Android device"
    private var rideCode: String = "RIDE01"
    private var labRole: LabRole = LabRole.NORMAL
    private var offlinePreferred = false
    @Volatile private var running = false
    @Volatile private var advertisingActive = false
    @Volatile private var discoveryActive = false
    @Volatile private var lastError = ""

    private val seenPackets: MutableMap<UUID, Boolean> = Collections.synchronizedMap(
        object : LinkedHashMap<UUID, Boolean>(1024, 0.75f, true) {
            override fun removeEldestEntry(eldest: MutableMap.MutableEntry<UUID, Boolean>?): Boolean {
                return size > 4096
            }
        }
    )

    private val payloadCallback = object : PayloadCallback() {
        override fun onPayloadReceived(endpointId: String, payload: Payload) {
            try {
                if (payload.type != Payload.Type.BYTES) return
                val raw = payload.asBytes() ?: return
                val packet = MeshPacket.decode(raw) ?: return
                receivedPackets.incrementAndGet()
                val observedHops = (MAX_TTL - packet.ttl + 1).coerceIn(1, MAX_TTL + 1)
                maxObservedHops.updateAndGet { previous -> maxOf(previous, observedHops) }

                synchronized(seenPackets) {
                    if (seenPackets.containsKey(packet.packetId)) return
                    seenPackets[packet.packetId] = true
                }

                if (packet.origin != nodeId) originEndpoints[packet.origin] = endpointId

                if (packet.origin != nodeId && packet.audio.isNotEmpty()) {
                    listener.onAudioPacket(packet.origin.toString(), packet.sequence, packet.timestampMs, packet.audio)
                }

                if (packet.ttl > 0) {
                    relayedPackets.incrementAndGet()
                    relay(packet.nextHop(), excludeEndpoint = endpointId)
                }
            } catch (t: Throwable) {
                listener.onLog("Payload error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")
            }
        }

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) = Unit
    }

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, info: ConnectionInfo) {
            endpointNames[endpointId] = info.endpointName
            val remoteCode = parseRideCode(info.endpointName)
            val remoteRole = parseLabRole(info.endpointName)
            try {
                if (remoteCode == rideCode && isAllowedPeer(remoteRole)) {
                    client.acceptConnection(endpointId, payloadCallback)
                    listener.onLog("Pairing with ${displayName(info.endpointName)}")
                } else {
                    client.rejectConnection(endpointId)
                }
            } catch (t: Throwable) {
                listener.onLog("Pairing error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")
            }
        }

        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {
            requested.remove(endpointId)
            if (resolution.status.isSuccess) {
                connected.add(endpointId)
                successfulConnections.incrementAndGet()
                lastError = ""
                listener.onLog("Connected: ${displayName(endpointNames[endpointId] ?: endpointId)}")
            } else {
                failedConnections.incrementAndGet()
                lastError = "Connection failed: status ${resolution.status.statusCode}"
                listener.onLog(lastError)
                scheduleDiscoveryRefresh("connection failed")
            }
            listener.onDirectPeerCount(connected.size)
        }

        override fun onDisconnected(endpointId: String) {
            connected.remove(endpointId)
            requested.remove(endpointId)
            originEndpoints.entries.removeIf { it.value == endpointId }
            listener.onLog("Peer disconnected: ${displayName(endpointNames[endpointId] ?: endpointId)}")
            listener.onDirectPeerCount(connected.size)
            if (running) scheduleDiscoveryRefresh("peer disconnected")
        }
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            val firstSeen = endpointNames.put(endpointId, info.endpointName) == null
            if (firstSeen) discoveredEndpoints.incrementAndGet()
            if (!running || parseRideCode(info.endpointName) != rideCode) return
            if (!isAllowedPeer(parseLabRole(info.endpointName))) return
            if (connected.contains(endpointId) || requested.contains(endpointId)) return

            if (shouldInitiate(info.endpointName)) {
                requestPeer(endpointId, info.endpointName, delayed = false)
            } else {
                listener.onLog("Found ${displayName(info.endpointName)} • waiting for peer handshake")
                Thread({
                    try { Thread.sleep(PASSIVE_CONNECT_DELAY_MS) } catch (_: InterruptedException) { return@Thread }
                    if (running && !connected.contains(endpointId) && !requested.contains(endpointId)) {
                        requestPeer(endpointId, info.endpointName, delayed = true)
                    }
                }, "RideMesh-PassiveConnect").apply { isDaemon = true; start() }
            }
        }

        override fun onEndpointLost(endpointId: String) {
            requested.remove(endpointId)
        }
    }

    private fun requestPeer(endpointId: String, endpointName: String, delayed: Boolean) {
        if (!running || connected.contains(endpointId) || !requested.add(endpointId)) return
        connectionAttempts.incrementAndGet()
        listener.onLog("Found ${displayName(endpointName)} — ${if (delayed) "retrying handshake" else "connecting"}")
        try {
            client.requestConnection(
                advertisedName(),
                endpointId,
                lifecycleCallback,
                ConnectionOptions.Builder()
                    .setConnectionType(connectionType())
                    .build(),
            ).addOnFailureListener { error ->
                requested.remove(endpointId)
                failedConnections.incrementAndGet()
                lastError = "Connection request: ${error.javaClass.simpleName}: ${error.message ?: "error"}"
                listener.onLog(lastError)
                scheduleDiscoveryRefresh("request failed")
            }
        } catch (t: Throwable) {
            requested.remove(endpointId)
            failedConnections.incrementAndGet()
            lastError = "Connection request: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"
            listener.onLog(lastError)
            scheduleDiscoveryRefresh("request exception")
        }
    }

    fun start(
        riderName: String,
        rideCode: String,
        labRole: LabRole = LabRole.NORMAL,
        deviceName: String = "",
        preferOffline: Boolean = false,
    ) {
        stop()
        this.riderName = sanitizeEndpointPart(riderName).ifBlank { "Rider" }.take(18)
        this.deviceName = sanitizeEndpointPart(deviceName).ifBlank { "Android device" }.take(40)
        this.rideCode = rideCode.trim().uppercase().ifBlank { "RIDE01" }.take(12)
        this.labRole = labRole
        this.offlinePreferred = preferOffline
        receivedPackets.set(0)
        relayedPackets.set(0)
        maxObservedHops.set(0)
        discoveredEndpoints.set(0)
        connectionAttempts.set(0)
        successfulConnections.set(0)
        failedConnections.set(0)
        sendFailures.set(0)
        advertisingActive = false
        discoveryActive = false
        lastError = ""
        running = true
        listener.onLog("Starting local mesh for ride ${this.rideCode} • ${if (preferOffline) "OFFLINE BALANCED" else "HYBRID"}")
        startNearbyEndpoints()
    }

    private fun startNearbyEndpoints() {
        if (!running) return
        val advertising = AdvertisingOptions.Builder()
            .setStrategy(STRATEGY)
            .setConnectionType(connectionType())
            .build()
        val discovery = DiscoveryOptions.Builder()
            .setStrategy(STRATEGY)
            .build()

        try {
            client.startAdvertising(advertisedName(), SERVICE_ID, lifecycleCallback, advertising)
                .addOnSuccessListener {
                    advertisingActive = true
                    listener.onLog("Local mesh advertising ACTIVE • ${this.riderName}")
                }
                .addOnFailureListener { error ->
                    advertisingActive = false
                    lastError = "Advertising: ${error.javaClass.simpleName}: ${error.message ?: "unknown"}"
                    listener.onLog(lastError)
                    scheduleDiscoveryRefresh("advertising failed")
                }

            client.startDiscovery(SERVICE_ID, discoveryCallback, discovery)
                .addOnSuccessListener {
                    discoveryActive = true
                    listener.onLog("Local mesh discovery ACTIVE")
                }
                .addOnFailureListener { error ->
                    discoveryActive = false
                    lastError = "Discovery: ${error.javaClass.simpleName}: ${error.message ?: "unknown"}"
                    listener.onLog(lastError)
                    scheduleDiscoveryRefresh("discovery failed")
                }
        } catch (t: Throwable) {
            advertisingActive = false
            discoveryActive = false
            lastError = "Nearby start: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"
            listener.onLog(lastError)
            scheduleDiscoveryRefresh("start exception")
        }
    }

    fun refreshDiscovery(reason: String) {
        if (!running) return
        listener.onLog("Refreshing Nearby advertising/discovery • $reason")
        scheduleDiscoveryRefresh(reason, delayMs = 0L)
    }

    private fun scheduleDiscoveryRefresh(reason: String, delayMs: Long = NEARBY_RETRY_DELAY_MS) {
        if (!running || !refreshScheduled.compareAndSet(false, true)) return
        Thread({
            try {
                if (delayMs > 0L) Thread.sleep(delayMs)
                if (!running) return@Thread
                runCatching { client.stopAdvertising() }
                runCatching { client.stopDiscovery() }
                advertisingActive = false
                discoveryActive = false
                Thread.sleep(NEARBY_REFRESH_SETTLE_MS)
                if (running) {
                    listener.onLog("Nearby retry • $reason")
                    startNearbyEndpoints()
                }
            } catch (_: InterruptedException) {
                // App/ride stopped.
            } finally {
                refreshScheduled.set(false)
            }
        }, "RideMesh-NearbyRetry").apply { isDaemon = true; start() }
    }

    fun stop() {
        running = false
        advertisingActive = false
        discoveryActive = false
        runCatching { client.stopAdvertising() }
        runCatching { client.stopDiscovery() }
        runCatching { client.stopAllEndpoints() }
        connected.clear()
        requested.clear()
        endpointNames.clear()
        originEndpoints.clear()
        listener.onDirectPeerCount(0)
    }

    fun diagnostics(): Diagnostics = Diagnostics(
        directPeers = connected.size,
        receivedPackets = receivedPackets.get(),
        relayedPackets = relayedPackets.get(),
        maxObservedHops = maxObservedHops.get(),
        advertisingActive = advertisingActive,
        discoveryActive = discoveryActive,
        discoveredEndpoints = discoveredEndpoints.get(),
        connectionAttempts = connectionAttempts.get(),
        successfulConnections = successfulConnections.get(),
        failedConnections = failedConnections.get(),
        pendingRequests = requested.size,
        sendFailures = sendFailures.get(),
        lastError = lastError,
        profile = if (offlinePreferred) "OFFLINE BALANCED" else "HYBRID NON-DISRUPTIVE",
    )

    private fun connectionType(): Int = if (offlinePreferred) {
        ConnectionType.BALANCED
    } else {
        ConnectionType.NON_DISRUPTIVE
    }

    fun endpointIdForSource(sourceId: String): String? = runCatching {
        originEndpoints[UUID.fromString(sourceId)]
    }.getOrNull()

    fun directPeers(): List<RiderPeer> = connected.mapNotNull { endpointId ->
        val endpointName = endpointNames[endpointId] ?: return@mapNotNull null
        RiderPeer(
            endpointId = endpointId,
            riderName = parseRiderName(endpointName),
            deviceName = parseDeviceName(endpointName),
        )
    }.sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName })

    fun sendLocalAudio(audio: ByteArray) {
        if (!running || audio.isEmpty() || connected.isEmpty()) return
        val packet = MeshPacket(
            ttl = MAX_TTL,
            origin = nodeId,
            packetId = UUID.randomUUID(),
            sequence = sequence.incrementAndGet(),
            timestampMs = System.currentTimeMillis(),
            audio = audio,
        )
        synchronized(seenPackets) { seenPackets[packet.packetId] = true }
        relay(packet, excludeEndpoint = null)
    }

    private fun relay(packet: MeshPacket, excludeEndpoint: String?) {
        val bytes = packet.encode()
        for (endpoint in connected) {
            if (endpoint == excludeEndpoint) continue
            try {
                client.sendPayload(endpoint, Payload.fromBytes(bytes))
                    .addOnFailureListener {
                        sendFailures.incrementAndGet()
                        lastError = "Send: ${it.javaClass.simpleName}: ${it.message ?: "unknown"}"
                        listener.onLog(lastError)
                    }
            } catch (t: Throwable) {
                sendFailures.incrementAndGet()
                lastError = "Send: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"
                listener.onLog(lastError)
            }
        }
    }

    private fun advertisedName(): String =
        "$rideCode|$riderName|${labRole.name}|${nodeId.toString().take(8)}|$deviceName"

    private fun parseRideCode(endpointName: String): String = endpointName.substringBefore('|').uppercase()

    private fun parseRiderName(endpointName: String): String {
        val parts = endpointName.split('|')
        return if (parts.size >= 2) parts[1].trim() else endpointName.trim()
    }

    private fun parseDeviceName(endpointName: String): String {
        val parts = endpointName.split('|')
        return if (parts.size >= 5) parts[4].trim() else ""
    }

    private fun sanitizeEndpointPart(value: String): String = value.trim().replace('|', '/')

    private fun parseNodeShort(endpointName: String): String {
        val parts = endpointName.split('|')
        return if (parts.size >= 4) parts[3].trim().lowercase() else ""
    }

    private fun shouldInitiate(endpointName: String): Boolean {
        val remote = parseNodeShort(endpointName)
        val local = nodeId.toString().take(8).lowercase()
        return remote.isBlank() || local <= remote
    }

    private fun parseLabRole(endpointName: String): LabRole {
        val parts = endpointName.split('|')
        return if (parts.size >= 3) {
            runCatching { LabRole.valueOf(parts[2].uppercase()) }.getOrDefault(LabRole.NORMAL)
        } else LabRole.NORMAL
    }

    private fun isAllowedPeer(remote: LabRole): Boolean {
        if (labRole == LabRole.NORMAL) return true
        return when (labRole) {
            LabRole.A -> remote == LabRole.B
            LabRole.B -> remote == LabRole.A || remote == LabRole.C
            LabRole.C -> remote == LabRole.B
            LabRole.NORMAL -> true
        }
    }

    private fun displayName(endpointName: String): String {
        val name = parseRiderName(endpointName)
        val role = parseLabRole(endpointName)
        return if (role == LabRole.NORMAL) name else "$name [${role.name}]"
    }

    companion object {
        private const val SERVICE_ID = "com.bikemesh.ridemesh.voice"
        private val STRATEGY = Strategy.P2P_CLUSTER
        private const val MAX_TTL = 4
        private const val PASSIVE_CONNECT_DELAY_MS = 900L
        private const val NEARBY_RETRY_DELAY_MS = 1_500L
        private const val NEARBY_REFRESH_SETTLE_MS = 650L
    }
}
