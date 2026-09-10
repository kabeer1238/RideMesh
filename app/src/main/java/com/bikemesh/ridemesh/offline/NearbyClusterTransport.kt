package com.bikemesh.ridemesh.offline

import android.content.Context
import android.os.SystemClock
import com.google.android.gms.nearby.Nearby
import com.google.android.gms.nearby.connection.AdvertisingOptions
import com.google.android.gms.nearby.connection.ConnectionInfo
import com.google.android.gms.nearby.connection.ConnectionLifecycleCallback
import com.google.android.gms.nearby.connection.ConnectionResolution
import com.google.android.gms.nearby.connection.ConnectionsClient
import com.google.android.gms.nearby.connection.DiscoveredEndpointInfo
import com.google.android.gms.nearby.connection.DiscoveryOptions
import com.google.android.gms.nearby.connection.EndpointDiscoveryCallback
import com.google.android.gms.nearby.connection.Payload
import com.google.android.gms.nearby.connection.PayloadCallback
import com.google.android.gms.nearby.connection.PayloadTransferUpdate
import com.google.android.gms.nearby.connection.Strategy
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/**
 * Android offline transport using Google Nearby Connections P2P_CLUSTER.
 *
 * This is deliberately isolated from RideMesh's existing Internet/WebRTC and map
 * paths. The ride token is used as the Nearby service namespace, so only riders
 * who entered/scanned the same ride code discover one another.
 *
 * Nearby owns radio selection/connection establishment. RideMesh owns identity,
 * health and (later) application-level multi-hop routing above this transport.
 */
class NearbyClusterTransport(
    context: Context,
    private val nodeId: String,
    private val riderName: String,
    private val rideToken: String,
    private val listener: Listener,
) {
    interface Listener {
        fun onStatus(message: String)
        fun onPeerConnected(nodeId: String, riderName: String)
        fun onPeerDisconnected(nodeId: String)
        fun onRtt(nodeId: String, rttMs: Int)
        fun onData(nodeId: String, payload: ByteArray)
    }

    private val client: ConnectionsClient = Nearby.getConnectionsClient(context.applicationContext)
    private val scheduler = Executors.newSingleThreadScheduledExecutor()
    private val connectedEndpoints = ConcurrentHashMap.newKeySet<String>()
    private val pendingEndpoints = ConcurrentHashMap.newKeySet<String>()
    private val endpointToNode = ConcurrentHashMap<String, String>()
    private val endpointToName = ConcurrentHashMap<String, String>()
    @Volatile private var started = false

    private val serviceId = "in.autopilotindia.ridemesh.offline.$rideToken"
    private val localEndpointName = riderName.ifBlank { "Rider" }.take(24)

    private val payloadCallback = object : PayloadCallback() {
        override fun onPayloadReceived(endpointId: String, payload: Payload) {
            val bytes = payload.asBytes() ?: return
            handleMessage(endpointId, bytes)
        }

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) = Unit
    }

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, info: ConnectionInfo) {
            if (!started) return
            endpointToName[endpointId] = info.endpointName.ifBlank { "Android rider" }
            listener.onStatus("OFFLINE NEARBY • authenticating ${endpointToName[endpointId]}")
            client.acceptConnection(endpointId, payloadCallback)
                .addOnFailureListener { listener.onStatus("OFFLINE NEARBY accept failed • ${shortError(it)}") }
        }

        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {
            pendingEndpoints.remove(endpointId)
            if (!started) return
            if (resolution.status.isSuccess) {
                connectedEndpoints.add(endpointId)
                listener.onStatus("OFFLINE NEARBY LINK READY • exchanging RideMesh identity")
                sendRaw(endpointId, hello())
            } else {
                listener.onStatus("OFFLINE NEARBY connection failed • ${resolution.status.statusCode}")
            }
        }

        override fun onDisconnected(endpointId: String) {
            connectedEndpoints.remove(endpointId)
            pendingEndpoints.remove(endpointId)
            val remoteNode = endpointToNode.remove(endpointId)
            endpointToName.remove(endpointId)
            if (remoteNode != null) listener.onPeerDisconnected(remoteNode)
            if (started) listener.onStatus("OFFLINE NEARBY PEER LOST • discovery continues")
        }
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            if (!started || connectedEndpoints.contains(endpointId) || !pendingEndpoints.add(endpointId)) return
            endpointToName[endpointId] = info.endpointName.ifBlank { "Android rider" }
            listener.onStatus("OFFLINE NEARBY FOUND • ${endpointToName[endpointId]}")
            client.requestConnection(localEndpointName, endpointId, lifecycleCallback)
                .addOnFailureListener {
                    pendingEndpoints.remove(endpointId)
                    // Simultaneous discovery can make both devices request at once. Nearby
                    // resolves the winning connection; keep discovery running rather than
                    // creating a second hotspot or forcing a role election.
                    listener.onStatus("OFFLINE NEARBY request retrying • ${shortError(it)}")
                }
        }

        override fun onEndpointLost(endpointId: String) {
            pendingEndpoints.remove(endpointId)
        }
    }

    fun start() {
        stop()
        started = true
        listener.onStatus("OFFLINE MESH • Nearby P2P_CLUSTER starting • no hotspot")

        val strategy = Strategy.P2P_CLUSTER
        client.startAdvertising(
            localEndpointName,
            serviceId,
            lifecycleCallback,
            AdvertisingOptions.Builder().setStrategy(strategy).build(),
        ).addOnSuccessListener {
            listener.onStatus("OFFLINE MESH • advertising same-code ride")
        }.addOnFailureListener {
            listener.onStatus("OFFLINE advertising failed • ${shortError(it)}")
        }

        client.startDiscovery(
            serviceId,
            discoveryCallback,
            DiscoveryOptions.Builder().setStrategy(strategy).build(),
        ).addOnSuccessListener {
            listener.onStatus("OFFLINE MESH • scanning for same-code riders")
        }.addOnFailureListener {
            listener.onStatus("OFFLINE discovery failed • ${shortError(it)}")
        }

        scheduler.scheduleAtFixedRate({
            if (!started) return@scheduleAtFixedRate
            val now = SystemClock.elapsedRealtime()
            connectedEndpoints.forEach { sendRaw(it, "PING|$now".toByteArray()) }
        }, 2, 2, TimeUnit.SECONDS)
    }

    fun stop() {
        started = false
        runCatching { client.stopAdvertising() }
        runCatching { client.stopDiscovery() }
        runCatching { client.stopAllEndpoints() }
        connectedEndpoints.clear()
        pendingEndpoints.clear()
        endpointToNode.clear()
        endpointToName.clear()
    }

    fun connectedPeerCount(): Int = endpointToNode.size

    fun firstPeerName(): String? = endpointToNode.keys.firstOrNull()?.let { node ->
        endpointToNode.entries.firstOrNull { it.value == node }?.key?.let(endpointToName::get)
    }

    fun send(payload: ByteArray): Boolean {
        val endpoints = connectedEndpoints.toList()
        if (endpoints.isEmpty()) return false
        val encoded = ByteArray(DATA_PREFIX.size + payload.size)
        DATA_PREFIX.copyInto(encoded)
        payload.copyInto(encoded, DATA_PREFIX.size)
        client.sendPayload(endpoints, Payload.fromBytes(encoded))
        return true
    }

    private fun handleMessage(endpointId: String, bytes: ByteArray) {
        val text = bytes.toString(Charsets.UTF_8)
        when {
            text.startsWith("HELLO|") -> {
                val parts = text.split('|', limit = 4)
                if (parts.size != 4 || parts[1] != rideToken || parts[2] == nodeId) {
                    client.disconnectFromEndpoint(endpointId)
                    return
                }
                val remoteNode = parts[2]
                val remoteName = parts[3].ifBlank { endpointToName[endpointId] ?: "Android rider" }
                val wasNew = endpointToNode.put(endpointId, remoteNode) == null
                endpointToName[endpointId] = remoteName
                if (wasNew) listener.onPeerConnected(remoteNode, remoteName)
            }

            text.startsWith("PING|") -> sendRaw(endpointId, "PONG|${text.substringAfter('|')}".toByteArray())
            text.startsWith("PONG|") -> {
                val sent = text.substringAfter('|').toLongOrNull() ?: return
                val remoteNode = endpointToNode[endpointId] ?: return
                val rtt = (SystemClock.elapsedRealtime() - sent).coerceIn(0, 60_000).toInt()
                listener.onRtt(remoteNode, rtt)
            }

            startsWith(bytes, DATA_PREFIX) -> {
                val remoteNode = endpointToNode[endpointId] ?: return
                listener.onData(remoteNode, bytes.copyOfRange(DATA_PREFIX.size, bytes.size))
            }
        }
    }

    private fun sendRaw(endpointId: String, bytes: ByteArray) {
        if (!connectedEndpoints.contains(endpointId)) return
        client.sendPayload(endpointId, Payload.fromBytes(bytes))
    }

    private fun hello(): ByteArray = "HELLO|$rideToken|$nodeId|${riderName.ifBlank { "Rider" }}".toByteArray()

    private fun startsWith(bytes: ByteArray, prefix: ByteArray): Boolean {
        if (bytes.size < prefix.size) return false
        for (i in prefix.indices) if (bytes[i] != prefix[i]) return false
        return true
    }

    private fun shortError(t: Throwable): String = t.message?.take(80) ?: t.javaClass.simpleName

    companion object {
        private val DATA_PREFIX = byteArrayOf(0x52, 0x4d, 0x44, 0x31) // RMD1
    }
}
