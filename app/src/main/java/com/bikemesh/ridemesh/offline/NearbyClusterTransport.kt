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
import java.util.concurrent.atomic.AtomicLong

/** Android offline transport using Google Nearby Connections P2P_CLUSTER. */
class NearbyClusterTransport(
    context: Context,
    private val nodeId: String,
    private val riderName: String,
    private val rideToken: String,
    deviceName: String = "Android device",
    private val listener: Listener,
    private val labRole: Int = 0,
) {
    interface Listener {
        fun onStatus(message: String)
        fun onPeerConnected(nodeId: String, riderName: String)
        fun onPeerDisconnected(nodeId: String)
        fun onRtt(nodeId: String, rttMs: Int)
        fun onData(nodeId: String, payload: ByteArray)
    }

    data class PeerSnapshot(
        val nodeId: String,
        val riderName: String,
        val deviceName: String,
    )

    private val client: ConnectionsClient = Nearby.getConnectionsClient(context.applicationContext)
    private var scheduler = Executors.newSingleThreadScheduledExecutor()
    private val connectedEndpoints = ConcurrentHashMap.newKeySet<String>()
    private val pendingEndpoints = ConcurrentHashMap.newKeySet<String>()
    private val endpointToNode = ConcurrentHashMap<String, String>()
    private val endpointToName = ConcurrentHashMap<String, String>()
    private val endpointToDevice = ConcurrentHashMap<String, String>()
    private val retryAfterMs = ConcurrentHashMap<String, Long>()
    private val helloAttempts = ConcurrentHashMap<String, Int>()

    // Realtime voice rule: never allow an unbounded Nearby BYTES backlog.
    // One audio payload may be in flight per peer. While it is transferring we
    // retain only the newest frame; older pending frames are discarded. For an
    // intercom, a missing 20 ms frame is far better than hearing speech seconds late.
    private val audioInFlightPayload = ConcurrentHashMap<String, Long>()
    private val audioLatestPending = ConcurrentHashMap<String, FreshAudioQueue>()
    private val audioSentAt = ConcurrentHashMap<String, Long>()
    private val foundEndpoints = ConcurrentHashMap<String, DiscoveredEndpointInfo>()
    private val pendingSince = ConcurrentHashMap<String, Long>()
    data class Stats(val advertising: Boolean, val discovering: Boolean, val found: Int,
        val attempts: Int, val connected: Int, val failed: Int, val pending: Int, val sendFailed: Int)
    @Volatile private var advertising = false
    @Volatile private var discovering = false
    private val attempts = java.util.concurrent.atomic.AtomicInteger()
    private val successful = java.util.concurrent.atomic.AtomicInteger()
    private val failures = java.util.concurrent.atomic.AtomicInteger()
    private val sendFailures = java.util.concurrent.atomic.AtomicInteger()
    fun stats() = Stats(advertising, discovering, foundEndpoints.size, attempts.get(), successful.get(), failures.get(), pendingEndpoints.size, sendFailures.get())
    fun refreshDiscovery(reason: String) { if (started) restartDiscovery() }
    private fun allowed(name: String): Boolean {
        val parts = name.split('|', limit = 4)
        if (parts.size != 4 || parts[0] != "RM34" || parts[2] != rideToken) return false
        val remote = parts[1].toIntOrNull() ?: return false
        return com.bikemesh.ridemesh.mesh.MeshRelayPolicy.allows(labRole, remote)
    }
    private val audioDropped = AtomicLong(0)

    @Volatile private var started = false

    private val serviceId = "in.autopilotindia.ridemesh.hybrid34"
    private val localEndpointName = "RM34|$labRole|$rideToken|${sanitize(riderName.ifBlank { "Rider" }).take(24)}"
    private val localDeviceName = sanitize(deviceName.ifBlank { "Android device" }).take(48)

    private fun status(message: String) = listener.onStatus("NEARBY DIAG • $message")

    private val payloadCallback = object : PayloadCallback() {
        override fun onPayloadReceived(endpointId: String, payload: Payload) {
            if (!started || endpointId !in connectedEndpoints) return
            val bytes = payload.asBytes() ?: return
            handleMessage(endpointId, bytes)
        }

        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) {
            if (!started || update.status == PayloadTransferUpdate.Status.IN_PROGRESS) return
            synchronized(audioInFlightPayload) {
                if (audioInFlightPayload[endpointId] != update.payloadId) return
                audioInFlightPayload.remove(endpointId)
                audioSentAt.remove(endpointId)
                if (update.status != PayloadTransferUpdate.Status.SUCCESS) sendFailures.incrementAndGet()
                drainAudio(endpointId)
            }
        }
    }

    private val lifecycleCallback = object : ConnectionLifecycleCallback() {
        override fun onConnectionInitiated(endpointId: String, info: ConnectionInfo) {
            if (!started) return
            if (!allowed(info.endpointName) || connectedEndpoints.size >= 7) {
                client.rejectConnection(endpointId)
                return
            }
            val name = info.endpointName.ifBlank { "Android rider" }
            endpointToName[endpointId] = name
            status("CONNECTION INITIATED • $name • ${endpointId.take(6)}")
            client.acceptConnection(endpointId, payloadCallback)
                .addOnSuccessListener { status("CONNECTION ACCEPTED • $name") }
                .addOnFailureListener { status("ACCEPT FAILED • ${shortError(it)}") }
        }

        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {
            pendingEndpoints.remove(endpointId)
            pendingSince.remove(endpointId)
            if (!started) return
            if (resolution.status.isSuccess) {
                successful.incrementAndGet()
                retryAfterMs.remove(endpointId)
                connectedEndpoints.add(endpointId)
                helloAttempts[endpointId] = 0
                status("CONNECTED • ${endpointToName[endpointId] ?: endpointId.take(6)} • exchanging identity")
                sendHello(endpointId)
            } else {
                failures.incrementAndGet()
                val code = resolution.status.statusCode
                retryAfterMs[endpointId] = SystemClock.elapsedRealtime() + RETRY_BACKOFF_MS
                status("CONNECTION FAILED • code=$code • retry in ${RETRY_BACKOFF_MS / 1000}s")
                if (connectedEndpoints.isEmpty()) {
                    scheduler.schedule({ restartDiscovery() }, RETRY_BACKOFF_MS, TimeUnit.MILLISECONDS)
                }
            }
        }

        override fun onDisconnected(endpointId: String) {
            if (!started) return
            audioSentAt.remove(endpointId)
            pendingSince.remove(endpointId)
            connectedEndpoints.remove(endpointId)
            pendingEndpoints.remove(endpointId)
            helloAttempts.remove(endpointId)
            audioInFlightPayload.remove(endpointId)
            audioLatestPending.remove(endpointId)?.let { audioDropped.addAndGet(it.droppedCount()) }
            val remoteNode = endpointToNode.remove(endpointId)
            val name = endpointToName.remove(endpointId)
            endpointToDevice.remove(endpointId)
            retryAfterMs[endpointId] = SystemClock.elapsedRealtime() + RETRY_BACKOFF_MS

            val isNodeStillConnected = remoteNode != null && endpointToNode.values.contains(remoteNode)
            if (remoteNode != null && !isNodeStillConnected) {
                listener.onPeerDisconnected(remoteNode)
            }

            if (started && connectedEndpoints.isEmpty()) {
                status("DISCONNECTED • ${name ?: endpointId.take(6)} • rediscovering")
                scheduler.schedule({ restartDiscovery() }, RETRY_BACKOFF_MS, TimeUnit.MILLISECONDS)
            }
        }
    }

    private val discoveryCallback = object : EndpointDiscoveryCallback() {
        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {
            if (!started || connectedEndpoints.contains(endpointId) || !allowed(info.endpointName)) return
            foundEndpoints[endpointId] = info
            val name = info.endpointName.ifBlank { "Android rider" }
            endpointToName[endpointId] = name
            status("ENDPOINT FOUND • $name • ${endpointId.take(6)}")

            if (connectedEndpoints.size >= 7) return

            val now = SystemClock.elapsedRealtime()
            val waitUntil = retryAfterMs[endpointId] ?: 0L
            if (now < waitUntil) {
                status("WAITING RETRY • $name • ${(waitUntil - now + 999) / 1000}s")
                return
            }

            // Keep the field-proven Build #24 behavior. Both peers may request and
            // Nearby resolves simultaneous requests; the passive/passive variant
            // previously deadlocked the Xiaomi test pair.
            if (!pendingEndpoints.add(endpointId)) return
            pendingSince[endpointId] = now
            attempts.incrementAndGet()
            status("REQUESTING CONNECTION • $name")
            client.requestConnection(localEndpointName, endpointId, lifecycleCallback)
                .addOnSuccessListener { status("REQUEST SENT • $name") }
                .addOnFailureListener {
                    if (!started) return@addOnFailureListener
                    pendingEndpoints.remove(endpointId)
                    pendingSince.remove(endpointId)
                    failures.incrementAndGet()
                    retryAfterMs[endpointId] = SystemClock.elapsedRealtime() + RETRY_BACKOFF_MS
                    status("REQUEST FAILED • ${shortError(it)} • retrying")
                    if (connectedEndpoints.isEmpty()) {
                        scheduler.schedule({ restartDiscovery() }, RETRY_BACKOFF_MS, TimeUnit.MILLISECONDS)
                    }
                }
        }

        override fun onEndpointLost(endpointId: String) {
            if (!started) return
            foundEndpoints.remove(endpointId)
            status("ENDPOINT LOST • ${endpointToName[endpointId] ?: endpointId.take(6)}")
        }
    }

    fun start() {
        stop()
        scheduler = Executors.newSingleThreadScheduledExecutor()
        started = true
        status("STARTING P2P_CLUSTER • service=${rideToken.take(8)} • no hotspot")
        val strategy = Strategy.P2P_CLUSTER

        client.startAdvertising(
            localEndpointName,
            serviceId,
            lifecycleCallback,
            AdvertisingOptions.Builder().setStrategy(strategy).build(),
        ).addOnSuccessListener {
            if (!started) return@addOnSuccessListener
            advertising = true
            status("ADVERTISING ON • $localEndpointName")
        }.addOnFailureListener {
            status("ADVERTISING FAILED • ${shortError(it)}")
        }

        client.startDiscovery(
            serviceId,
            discoveryCallback,
            DiscoveryOptions.Builder().setStrategy(strategy).build(),
        ).addOnSuccessListener {
            if (!started) return@addOnSuccessListener
            discovering = true
            status("DISCOVERY ON • searching same-code riders")
        }.addOnFailureListener {
            status("DISCOVERY FAILED • ${shortError(it)}")
        }

        scheduler.scheduleWithFixedDelay({
            if (!started) return@scheduleWithFixedDelay
            val now = SystemClock.elapsedRealtime()
            pendingSince.entries.filter { now - it.value > 12_000 }.forEach {
                pendingSince.remove(it.key); pendingEndpoints.remove(it.key)
                client.disconnectFromEndpoint(it.key)
                retryAfterMs[it.key] = now + RETRY_BACKOFF_MS
            }
            audioSentAt.entries.filter { now - it.value > 1500 }.forEach {
                audioSentAt.remove(it.key)
                audioInFlightPayload.remove(it.key)?.let(client::cancelPayload)
                client.disconnectFromEndpoint(it.key)
                sendFailures.incrementAndGet()
            }
            foundEndpoints.forEach { (endpoint, info) -> discoveryCallback.onEndpointFound(endpoint, info) }
            connectedEndpoints.forEach { endpointId ->
                synchronized(audioInFlightPayload) { drainAudio(endpointId) }
                if (!endpointToNode.containsKey(endpointId)) {
                    if ((helloAttempts[endpointId] ?: 0) >= 10) client.disconnectFromEndpoint(endpointId)
                    else sendHello(endpointId)
                } else sendRaw(endpointId, "PING|$now".toByteArray())
            }
        }, 1, 1, TimeUnit.SECONDS)
    }

    fun stop() {
        started = false
        scheduler.shutdownNow()
        advertising = false; discovering = false
        foundEndpoints.clear(); pendingSince.clear(); audioSentAt.clear()
        runCatching { client.stopAdvertising() }
        runCatching { client.stopDiscovery() }
        runCatching { client.stopAllEndpoints() }
        connectedEndpoints.clear()
        pendingEndpoints.clear()
        endpointToNode.clear()
        endpointToName.clear()
        endpointToDevice.clear()
        retryAfterMs.clear()
        helloAttempts.clear()
        audioInFlightPayload.clear()
        audioLatestPending.clear()
        audioDropped.set(0)
    }

    fun connectedPeerCount(): Int = endpointToNode.size
    fun firstPeerName(): String? = endpointToNode.entries.firstOrNull()?.key?.let(endpointToName::get)
    fun realtimeAudioDropped(): Long = audioDropped.get() + audioLatestPending.values.sumOf { it.droppedCount() }

    fun peerSnapshots(): List<PeerSnapshot> = endpointToNode.entries.map { (endpointId, remoteNodeId) ->
        PeerSnapshot(
            nodeId = remoteNodeId,
            riderName = endpointToName[endpointId].orEmpty().ifBlank { "Android rider" },
            deviceName = endpointToDevice[endpointId].orEmpty().ifBlank { "Android device" },
        )
    }.sortedBy { it.riderName.lowercase() }

    @Suppress("unused")
    fun send(payload: ByteArray): Boolean = sendExceptNode(null, payload)

    fun sendExceptNode(excludedNodeId: String?, payload: ByteArray): Boolean {
        if (!started) return false
        val endpoints = connectedEndpoints.filter { endpointId ->
            val peerNodeId = endpointToNode[endpointId]
            peerNodeId != null && peerNodeId != excludedNodeId
        }
        if (endpoints.isEmpty()) return false

        val encoded = ByteArray(DATA_PREFIX.size + payload.size)
        DATA_PREFIX.copyInto(encoded)
        payload.copyInto(encoded, DATA_PREFIX.size)

        val envelope = RideMeshEnvelope.decode(payload) ?: return false
        if (envelope.type == RideMeshEnvelope.Type.AUDIO) {
            synchronized(audioInFlightPayload) {
                for (endpoint in endpoints) {
                    audioLatestPending.computeIfAbsent(endpoint) { FreshAudioQueue() }
                        .offer(envelope.originNodeId.toString(), encoded, SystemClock.elapsedRealtime())
                    drainAudio(endpoint)
                }
            }
        } else {
            client.sendPayload(endpoints, Payload.fromBytes(encoded))
                .addOnFailureListener { sendFailures.incrementAndGet() }
        }
        return true
    }

    private fun drainAudio(endpoint: String) {
        if (!started || endpoint !in connectedEndpoints || audioInFlightPayload.containsKey(endpoint)) return
        val bytes = audioLatestPending[endpoint]?.poll(SystemClock.elapsedRealtime()) ?: return
        val payload = Payload.fromBytes(bytes)
        audioInFlightPayload[endpoint] = payload.id
        audioSentAt[endpoint] = SystemClock.elapsedRealtime()
        client.sendPayload(endpoint, payload).addOnFailureListener {
            synchronized(audioInFlightPayload) {
                if (audioInFlightPayload[endpoint] == payload.id) {
                    audioInFlightPayload.remove(endpoint); audioSentAt.remove(endpoint)
                    sendFailures.incrementAndGet()
                    // The periodic tick or next capture retries; do not recurse on immediate failures.
                }
            }
        }
    }

    private fun restartDiscovery() {
        if (!started) return
        runCatching { client.stopDiscovery() }
        discovering = false
        if (!advertising) {
            client.startAdvertising(localEndpointName, serviceId, lifecycleCallback,
                AdvertisingOptions.Builder().setStrategy(Strategy.P2P_CLUSTER).build())
                .addOnSuccessListener { if (started) advertising = true }
                .addOnFailureListener { if (started) status("ADVERTISING RETRY FAILED • ${shortError(it)}") }
        }
        client.startDiscovery(
            serviceId,
            discoveryCallback,
            DiscoveryOptions.Builder().setStrategy(Strategy.P2P_CLUSTER).build(),
        ).addOnSuccessListener {
            discovering = true
            status("DISCOVERY RESTARTED • searching same-code riders")
        }.addOnFailureListener {
            status("DISCOVERY RESTART FAILED • ${shortError(it)}")
        }
    }

    private fun handleMessage(endpointId: String, bytes: ByteArray) {
        if (!started || endpointId !in connectedEndpoints || bytes.size > RideMeshEnvelope.MAX_PAYLOAD + 100) return
        if (startsWith(bytes, DATA_PREFIX)) {
            endpointToNode[endpointId]?.let { listener.onData(it, bytes.copyOfRange(DATA_PREFIX.size, bytes.size)) }
            return
        }
        val text = bytes.toString(Charsets.UTF_8)
        when {
            text.startsWith("HELLO|") -> {
                val parts = text.split('|', limit = 5)
                if (!acceptIdentity(endpointId, parts)) return
                sendRaw(endpointId, helloAck())
            }
            text.startsWith("HELLO_ACK|") -> acceptIdentity(endpointId, text.split('|', limit = 5))
            text.startsWith("PING|") -> sendRaw(endpointId, "PONG|${text.substringAfter('|')}".toByteArray())
            text.startsWith("PONG|") -> {
                val sent = text.substringAfter('|').toLongOrNull() ?: return
                val remoteNode = endpointToNode[endpointId] ?: return
                listener.onRtt(remoteNode, (SystemClock.elapsedRealtime() - sent).coerceIn(0, 60_000).toInt())
            }
            startsWith(bytes, DATA_PREFIX) -> endpointToNode[endpointId]?.let {
                listener.onData(it, bytes.copyOfRange(DATA_PREFIX.size, bytes.size))
            }
        }
    }

    private fun acceptIdentity(endpointId: String, parts: List<String>): Boolean {
        if (parts.size < 4 || parts[1] != rideToken || parts[2] == nodeId) {
            status("IDENTITY REJECTED • endpoint=${endpointId.take(6)}")
            client.disconnectFromEndpoint(endpointId)
            return false
        }
        val remoteNode = parts[2]
        if (runCatching { java.util.UUID.fromString(remoteNode) }.isFailure) {
            client.disconnectFromEndpoint(endpointId)
            return false
        }
        val remoteName = parts[3].ifBlank { endpointToName[endpointId] ?: "Android rider" }
        val remoteDevice = parts.getOrNull(4).orEmpty().ifBlank { "Android device" }

        val existingEndpoint = endpointToNode.entries.firstOrNull { it.value == remoteNode && it.key != endpointId }?.key
        if (existingEndpoint != null && connectedEndpoints.contains(existingEndpoint)) {
            status("DUPLICATE ENDPOINT • keeping $existingEndpoint • closing $endpointId")
            client.disconnectFromEndpoint(endpointId)
            return false
        }

        val wasNew = endpointToNode.put(endpointId, remoteNode) == null
        endpointToName[endpointId] = remoteName
        endpointToDevice[endpointId] = remoteDevice
        helloAttempts.remove(endpointId)
        if (wasNew) {
            status("IDENTITY OK • $remoteName • $remoteDevice • RIDERS ${endpointToNode.size + 1}")
            listener.onPeerConnected(remoteNode, remoteName)
        }
        return true
    }

    private fun sendHello(endpointId: String) {
        val attempt = (helloAttempts[endpointId] ?: 0) + 1
        helloAttempts[endpointId] = attempt
        if (attempt == 1 || attempt == 3 || attempt == 5) {
            status("IDENTITY HELLO • ${endpointToName[endpointId] ?: endpointId.take(6)} • attempt $attempt")
        }
        sendRaw(endpointId, hello())
    }

    private fun sendRaw(endpointId: String, bytes: ByteArray) {
        if (connectedEndpoints.contains(endpointId)) {
            client.sendPayload(endpointId, Payload.fromBytes(bytes))
                .addOnFailureListener { status("PAYLOAD SEND FAILED • ${shortError(it)}") }
        }
    }

    private fun hello() = "HELLO|$rideToken|$nodeId|${sanitize(riderName.ifBlank { "Rider" })}|$localDeviceName".toByteArray()
    private fun helloAck() = "HELLO_ACK|$rideToken|$nodeId|${sanitize(riderName.ifBlank { "Rider" })}|$localDeviceName".toByteArray()
    private fun sanitize(value: String): String = value.replace('|', '/').replace('\n', ' ').replace('\r', ' ')
    @Suppress("SameParameterValue")
    private fun startsWith(bytes: ByteArray, prefix: ByteArray): Boolean = bytes.size >= prefix.size && prefix.indices.all { bytes[it] == prefix[it] }
    private fun shortError(t: Throwable): String = "${t.javaClass.simpleName}: ${t.message.orEmpty().take(90)}"

    companion object {
        private const val RETRY_BACKOFF_MS = 3500L
        private val DATA_PREFIX = byteArrayOf(0x52, 0x4d, 0x44, 0x31)
    }
}
