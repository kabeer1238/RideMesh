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

/** Android offline transport using Google Nearby Connections P2P_CLUSTER. */
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

    private fun status(message: String) = listener.onStatus("NEARBY DIAG • $message")

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
            val name = info.endpointName.ifBlank { "Android rider" }
            endpointToName[endpointId] = name
            status("CONNECTION INITIATED • $name • ${endpointId.take(6)}")
            client.acceptConnection(endpointId, payloadCallback)
                .addOnSuccessListener { status("CONNECTION ACCEPTED • $name") }
                .addOnFailureListener { status("ACCEPT FAILED • ${shortError(it)}") }
        }

        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {
            pendingEndpoints.remove(endpointId)
            if (!started) return
            if (resolution.status.isSuccess) {
                connectedEndpoints.add(endpointId)
                status("CONNECTED • ${endpointToName[endpointId] ?: endpointId.take(6)} • exchanging identity")
                sendRaw(endpointId, hello())
            } else {
                status("CONNECTION FAILED • code=${resolution.status.statusCode} • ${resolution.status.statusMessage.orEmpty().take(60)}")
            }
        }

        override fun onDisconnected(endpointId: String) {
            connectedEndpoints.remove(endpointId)
            pendingEndpoints.remove(endpointId)
            val remoteNode = endpointToNode.remove(endpointId)
            val name = endpointToName.remove(endpointId)
            if (remoteNode != null) listener.onPeerDisconnected(remoteNode)
            if (started) status("DISCONNECTED • ${name ?: endpointId.take(6)} • discovery continues")
        }
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            if (!started || connectedEndpoints.contains(endpointId) || !pendingEndpoints.add(endpointId)) return
            val name = info.endpointName.ifBlank { "Android rider" }
            endpointToName[endpointId] = name
            status("ENDPOINT FOUND • $name • ${endpointId.take(6)}")
            status("REQUESTING CONNECTION • $name")
            client.requestConnection(localEndpointName, endpointId, lifecycleCallback)
                .addOnSuccessListener { status("REQUEST SENT • $name") }
                .addOnFailureListener {
                    pendingEndpoints.remove(endpointId)
                    status("REQUEST FAILED • ${shortError(it)} • discovery remains active")
                }
        }

        override fun onEndpointLost(endpointId: String) {
            pendingEndpoints.remove(endpointId)
            status("ENDPOINT LOST • ${endpointToName[endpointId] ?: endpointId.take(6)}")
        }
    }

    fun start() {
        stop()
        started = true
        status("STARTING P2P_CLUSTER • service=${rideToken.take(8)} • no hotspot")
        val strategy = Strategy.P2P_CLUSTER

        client.startAdvertising(localEndpointName, serviceId, lifecycleCallback,
            AdvertisingOptions.Builder().setStrategy(strategy).build())
            .addOnSuccessListener { status("ADVERTISING ON • $localEndpointName") }
            .addOnFailureListener { status("ADVERTISING FAILED • ${shortError(it)}") }

        client.startDiscovery(serviceId, discoveryCallback,
            DiscoveryOptions.Builder().setStrategy(strategy).build())
            .addOnSuccessListener { status("DISCOVERY ON • searching same-code riders") }
            .addOnFailureListener { status("DISCOVERY FAILED • ${shortError(it)}") }

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
        connectedEndpoints.clear(); pendingEndpoints.clear(); endpointToNode.clear(); endpointToName.clear()
    }

    fun connectedPeerCount(): Int = endpointToNode.size
    fun firstPeerName(): String? = endpointToNode.entries.firstOrNull()?.key?.let(endpointToName::get)

    fun send(payload: ByteArray): Boolean {
        val endpoints = connectedEndpoints.toList()
        if (endpoints.isEmpty()) return false
        val encoded = ByteArray(DATA_PREFIX.size + payload.size)
        DATA_PREFIX.copyInto(encoded); payload.copyInto(encoded, DATA_PREFIX.size)
        client.sendPayload(endpoints, Payload.fromBytes(encoded))
        return true
    }

    private fun handleMessage(endpointId: String, bytes: ByteArray) {
        val text = bytes.toString(Charsets.UTF_8)
        when {
            text.startsWith("HELLO|") -> {
                val parts = text.split('|', limit = 4)
                if (parts.size != 4 || parts[1] != rideToken || parts[2] == nodeId) {
                    status("HELLO REJECTED • endpoint=${endpointId.take(6)}")
                    client.disconnectFromEndpoint(endpointId); return
                }
                val remoteNode = parts[2]
                val remoteName = parts[3].ifBlank { endpointToName[endpointId] ?: "Android rider" }
                val wasNew = endpointToNode.put(endpointId, remoteNode) == null
                endpointToName[endpointId] = remoteName
                if (wasNew) {
                    status("IDENTITY OK • $remoteName")
                    listener.onPeerConnected(remoteNode, remoteName)
                }
            }
            text.startsWith("PING|") -> sendRaw(endpointId, "PONG|${text.substringAfter('|')}".toByteArray())
            text.startsWith("PONG|") -> {
                val sent = text.substringAfter('|').toLongOrNull() ?: return
                val remoteNode = endpointToNode[endpointId] ?: return
                listener.onRtt(remoteNode, (SystemClock.elapsedRealtime() - sent).coerceIn(0, 60_000).toInt())
            }
            startsWith(bytes, DATA_PREFIX) -> endpointToNode[endpointId]?.let { listener.onData(it, bytes.copyOfRange(DATA_PREFIX.size, bytes.size)) }
        }
    }

    private fun sendRaw(endpointId: String, bytes: ByteArray) {
        if (connectedEndpoints.contains(endpointId)) client.sendPayload(endpointId, Payload.fromBytes(bytes))
    }
    private fun hello() = "HELLO|$rideToken|$nodeId|${riderName.ifBlank { "Rider" }}".toByteArray()
    private fun startsWith(bytes: ByteArray, prefix: ByteArray): Boolean = bytes.size >= prefix.size && prefix.indices.all { bytes[it] == prefix[it] }
    private fun shortError(t: Throwable): String = "${t.javaClass.simpleName}: ${t.message.orEmpty().take(90)}"

    companion object { private val DATA_PREFIX = byteArrayOf(0x52, 0x4d, 0x44, 0x31) }
}
