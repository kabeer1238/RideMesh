package com.bikemesh.ridemesh.transport

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.NetworkSpecifier
import android.net.wifi.aware.AttachCallback
import android.net.wifi.aware.DiscoverySession
import android.net.wifi.aware.DiscoverySessionCallback
import android.net.wifi.aware.PeerHandle
import android.net.wifi.aware.PublishConfig
import android.net.wifi.aware.PublishDiscoverySession
import android.net.wifi.aware.SubscribeConfig
import android.net.wifi.aware.SubscribeDiscoverySession
import android.net.wifi.aware.WifiAwareManager
import android.net.wifi.aware.WifiAwareNetworkInfo
import android.net.wifi.aware.WifiAwareNetworkSpecifier
import android.net.wifi.aware.WifiAwareSession
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import androidx.core.content.ContextCompat
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.Collections
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

/**
 * Android Wi-Fi Aware transport for RideMesh offline links.
 *
 * This class deliberately keeps the RideMesh payload opaque. It creates a NAN
 * discovery/data path, establishes TCP, performs a small cross-platform
 * handshake, then forwards framed envelope bytes to RideMeshTransport.Listener.
 *
 * Both Android devices publish and subscribe. A deterministic node-id ordering
 * prevents duplicate A<->B connections: the lexicographically larger node acts
 * as the NAN initiator/subscriber and the smaller node responds/publishes.
 *
 * Phase 1 uses an open NAN data path so the Android and iOS implementations can
 * prove standards-level interoperability first. Before voice payloads ship, the
 * framed connection must be upgraded with authenticated end-to-end encryption.
 */
class WifiAwareTransport(
    context: Context,
    nodeId: String,
    riderName: String,
    rideCode: String,
) : RideMeshTransport {

    override val kind: TransportKind = TransportKind.WIFI_AWARE
    override val capabilities = TransportCapabilities(
        supportsDiscovery = true,
        supportsMultiplePeers = true,
        supportsInternetReach = false,
        supportsBackgroundUse = true,
    )

    @Volatile
    override var state: TransportState = TransportState.STOPPED
        private set

    private val appContext = context.applicationContext
    private val awareManager = appContext.getSystemService(Context.WIFI_AWARE_SERVICE) as? WifiAwareManager
    private val connectivityManager = appContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val mainHandler = Handler(Looper.getMainLooper())
    private val identity = WifiAwareWireProtocol.Identity(
        nodeId = nodeId,
        rideToken = WifiAwareWireProtocol.rideToken(rideCode),
        riderName = riderName.ifBlank { "Rider" },
    )

    @Volatile
    private var listener: RideMeshTransport.Listener? = null

    @Volatile
    private var started = false

    @Volatile
    private var awareSession: WifiAwareSession? = null

    @Volatile
    private var publishSession: PublishDiscoverySession? = null

    @Volatile
    private var subscribeSession: SubscribeDiscoverySession? = null

    private val ioExecutor = Executors.newCachedThreadPool()
    private val heartbeatExecutor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
    private val networkCallbacks = Collections.synchronizedSet(mutableSetOf<ConnectivityManager.NetworkCallback>())
    private val requestedResponderPeers = ConcurrentHashMap.newKeySet<Int>()
    private val requestedInitiatorPeers = ConcurrentHashMap.newKeySet<Int>()
    private val knownIdentities = ConcurrentHashMap<Int, WifiAwareWireProtocol.Identity>()
    private val links = ConcurrentHashMap<String, PeerLink>()
    private val lastRttByPeer = ConcurrentHashMap<String, Int>()
    private val nextMessageId = AtomicLong(1L)
    private val receiverRegistered = AtomicBoolean(false)

    @Volatile
    private var serverSocket: ServerSocket? = null

    private val awareStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action != WifiAwareManager.ACTION_WIFI_AWARE_STATE_CHANGED || !started) return
            if (awareManager?.isAvailable == true) {
                if (awareSession == null) attachAware()
            } else {
                closeAwareSessions()
                changeState(TransportState.UNAVAILABLE)
            }
        }
    }

    override fun setListener(listener: RideMeshTransport.Listener?) {
        this.listener = listener
    }

    override fun start() {
        if (started) return
        started = true
        changeState(TransportState.STARTING)

        if (!appContext.packageManager.hasSystemFeature(PackageManager.FEATURE_WIFI_AWARE)) {
            changeState(TransportState.UNAVAILABLE)
            return
        }
        if (!hasAwarePermission()) {
            changeState(TransportState.UNAVAILABLE)
            return
        }
        if (awareManager == null || !awareManager.isAvailable) {
            changeState(TransportState.UNAVAILABLE)
            registerAwareReceiver()
            return
        }

        registerAwareReceiver()
        startHeartbeatLoop()
        attachAware()
    }

    override fun stop() {
        if (!started && state == TransportState.STOPPED) return
        started = false
        closeAwareSessions()
        closeAllLinks()
        closeServer()
        unregisterNetworkCallbacks()
        requestedResponderPeers.clear()
        requestedInitiatorPeers.clear()
        knownIdentities.clear()
        lastRttByPeer.clear()
        unregisterAwareReceiver()
        changeState(TransportState.STOPPED)
        publishMetrics()
    }

    override fun send(envelope: ByteArray, destinationNodeId: String?): Boolean {
        if (!started || envelope.isEmpty() || envelope.size + 1 > WifiAwareWireProtocol.MAX_FRAME_BYTES) {
            return false
        }
        return if (destinationNodeId != null) {
            links[destinationNodeId]?.sendData(envelope) == true
        } else {
            var sent = false
            links.values.forEach { link ->
                sent = link.sendData(envelope) || sent
            }
            sent
        }
    }

    private fun attachAware() {
        val manager = awareManager ?: return
        if (!started || awareSession != null) return
        try {
            manager.attach(object : AttachCallback() {
                override fun onAttached(session: WifiAwareSession) {
                    if (!started) {
                        session.close()
                        return
                    }
                    awareSession = session
                    beginDiscovery(session)
                }

                override fun onAttachFailed() {
                    awareSession = null
                    changeState(TransportState.DEGRADED)
                }
            }, mainHandler)
        } catch (_: SecurityException) {
            changeState(TransportState.UNAVAILABLE)
        } catch (_: RuntimeException) {
            changeState(TransportState.DEGRADED)
        }
    }

    private fun beginDiscovery(session: WifiAwareSession) {
        val advertisedIdentity = WifiAwareWireProtocol.encodeDiscovery(
            WifiAwareWireProtocol.DiscoveryMessageKind.IDENTITY,
            identity,
        )

        val publishConfig = PublishConfig.Builder()
            .setServiceName(WifiAwareWireProtocol.SERVICE_NAME)
            .setServiceSpecificInfo(advertisedIdentity)
            .build()

        val subscribeConfig = SubscribeConfig.Builder()
            .setServiceName(WifiAwareWireProtocol.SERVICE_NAME)
            .build()

        session.publish(publishConfig, object : DiscoverySessionCallback() {
            override fun onPublishStarted(session: PublishDiscoverySession) {
                publishSession = session
                if (subscribeSession != null) changeState(TransportState.AVAILABLE)
            }

            override fun onSessionConfigFailed() {
                changeState(TransportState.DEGRADED)
            }

            override fun onSessionTerminated() {
                publishSession = null
                if (started) changeState(TransportState.DEGRADED)
            }

            override fun onMessageReceived(peerHandle: PeerHandle, message: ByteArray) {
                val decoded = WifiAwareWireProtocol.decodeDiscovery(message) ?: return
                if (!isCompatible(decoded.identity)) return
                knownIdentities[peerHandle.hashCode()] = decoded.identity

                if (decoded.kind == WifiAwareWireProtocol.DiscoveryMessageKind.HELLO &&
                    identity.nodeId < decoded.identity.nodeId
                ) {
                    requestResponderDataPath(session = publishSession ?: return, peerHandle = peerHandle)
                    publishSession?.sendMessage(
                        peerHandle,
                        nextAwareMessageId(),
                        WifiAwareWireProtocol.encodeDiscovery(
                            WifiAwareWireProtocol.DiscoveryMessageKind.READY,
                            identity,
                        ),
                    )
                }
            }
        }, mainHandler)

        session.subscribe(subscribeConfig, object : DiscoverySessionCallback() {
            override fun onSubscribeStarted(session: SubscribeDiscoverySession) {
                subscribeSession = session
                if (publishSession != null) changeState(TransportState.AVAILABLE)
            }

            override fun onSessionConfigFailed() {
                changeState(TransportState.DEGRADED)
            }

            override fun onSessionTerminated() {
                subscribeSession = null
                if (started) changeState(TransportState.DEGRADED)
            }

            override fun onServiceDiscovered(
                peerHandle: PeerHandle,
                serviceSpecificInfo: ByteArray,
                matchFilter: MutableList<ByteArray>,
            ) {
                val discovered = WifiAwareWireProtocol.decodeDiscovery(serviceSpecificInfo) ?: return
                if (!isCompatible(discovered.identity)) return
                knownIdentities[peerHandle.hashCode()] = discovered.identity

                // Per NAN roles, subscriber is initiator. Only the larger node-id
                // initiates so two devices don't build two mirror connections.
                if (identity.nodeId > discovered.identity.nodeId) {
                    subscribeSession?.sendMessage(
                        peerHandle,
                        nextAwareMessageId(),
                        WifiAwareWireProtocol.encodeDiscovery(
                            WifiAwareWireProtocol.DiscoveryMessageKind.HELLO,
                            identity,
                        ),
                    )
                }
            }

            override fun onMessageReceived(peerHandle: PeerHandle, message: ByteArray) {
                val decoded = WifiAwareWireProtocol.decodeDiscovery(message) ?: return
                if (!isCompatible(decoded.identity)) return
                knownIdentities[peerHandle.hashCode()] = decoded.identity

                if (decoded.kind == WifiAwareWireProtocol.DiscoveryMessageKind.READY &&
                    identity.nodeId > decoded.identity.nodeId
                ) {
                    requestInitiatorDataPath(
                        session = subscribeSession ?: return,
                        peerHandle = peerHandle,
                        expectedIdentity = decoded.identity,
                    )
                }
            }
        }, mainHandler)
    }

    private fun requestResponderDataPath(session: DiscoverySession, peerHandle: PeerHandle) {
        val peerKey = peerHandle.hashCode()
        if (!requestedResponderPeers.add(peerKey)) return
        ensureServerRunning()

        val request = createAwareNetworkRequest(session, peerHandle)
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                changeState(TransportState.AVAILABLE)
            }

            override fun onLost(network: Network) {
                requestedResponderPeers.remove(peerKey)
            }

            override fun onUnavailable() {
                requestedResponderPeers.remove(peerKey)
                publishMetrics()
            }
        }
        requestNetwork(request, callback)
    }

    private fun requestInitiatorDataPath(
        session: DiscoverySession,
        peerHandle: PeerHandle,
        expectedIdentity: WifiAwareWireProtocol.Identity,
    ) {
        val peerKey = peerHandle.hashCode()
        if (!requestedInitiatorPeers.add(peerKey)) return

        val request = createAwareNetworkRequest(session, peerHandle)
        val callback = object : ConnectivityManager.NetworkCallback() {
            private val connected = AtomicBoolean(false)

            override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
                if (!connected.compareAndSet(false, true)) return
                val awareInfo = capabilities.transportInfo as? WifiAwareNetworkInfo
                val address = awareInfo?.peerIpv6Addr
                if (address == null) {
                    connected.set(false)
                    return
                }
                ioExecutor.execute {
                    try {
                        val socket = network.socketFactory.createSocket()
                        socket.tcpNoDelay = true
                        socket.connect(InetSocketAddress(address, WifiAwareWireProtocol.TCP_PORT), CONNECT_TIMEOUT_MS)
                        startPeerLink(socket, expectedIdentity)
                    } catch (_: Throwable) {
                        connected.set(false)
                    }
                }
            }

            override fun onLost(network: Network) {
                requestedInitiatorPeers.remove(peerKey)
                links[expectedIdentity.nodeId]?.close()
            }

            override fun onUnavailable() {
                requestedInitiatorPeers.remove(peerKey)
                publishMetrics()
            }
        }
        requestNetwork(request, callback)
    }

    private fun createAwareNetworkRequest(session: DiscoverySession, peerHandle: PeerHandle): NetworkRequest {
        val specifier: NetworkSpecifier = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            WifiAwareNetworkSpecifier.Builder(session, peerHandle).build()
        } else {
            @Suppress("DEPRECATION")
            session.createNetworkSpecifierOpen(peerHandle)
        }
        return NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI_AWARE)
            .setNetworkSpecifier(specifier)
            .build()
    }

    private fun requestNetwork(request: NetworkRequest, callback: ConnectivityManager.NetworkCallback) {
        networkCallbacks.add(callback)
        try {
            connectivityManager.requestNetwork(request, callback)
        } catch (_: Throwable) {
            networkCallbacks.remove(callback)
            changeState(TransportState.DEGRADED)
        }
    }

    private fun ensureServerRunning() {
        if (serverSocket?.isClosed == false) return
        synchronized(this) {
            if (serverSocket?.isClosed == false) return
            try {
                val server = ServerSocket().apply {
                    reuseAddress = true
                    bind(InetSocketAddress(WifiAwareWireProtocol.TCP_PORT))
                }
                serverSocket = server
                ioExecutor.execute {
                    while (started && !server.isClosed) {
                        try {
                            val socket = server.accept().apply { tcpNoDelay = true }
                            startPeerLink(socket, null)
                        } catch (_: Throwable) {
                            if (!started || server.isClosed) break
                        }
                    }
                }
            } catch (_: Throwable) {
                changeState(TransportState.DEGRADED)
            }
        }
    }

    private fun startPeerLink(socket: Socket, expectedIdentity: WifiAwareWireProtocol.Identity?) {
        val link = PeerLink(socket, expectedIdentity)
        link.start()
    }

    private inner class PeerLink(
        private val socket: Socket,
        private val expectedIdentity: WifiAwareWireProtocol.Identity?,
    ) {
        private val closed = AtomicBoolean(false)
        private val input = DataInputStream(socket.getInputStream())
        private val output = DataOutputStream(socket.getOutputStream())

        @Volatile
        private var remoteIdentity: WifiAwareWireProtocol.Identity? = null

        fun start() {
            try {
                WifiAwareWireProtocol.writeFrame(
                    output,
                    WifiAwareWireProtocol.TYPE_HELLO,
                    WifiAwareWireProtocol.encodeIdentity(identity),
                )
            } catch (_: Throwable) {
                close()
                return
            }

            ioExecutor.execute {
                try {
                    while (!closed.get()) {
                        val frame = WifiAwareWireProtocol.readFrame(input) ?: break
                        handleFrame(frame.first, frame.second)
                    }
                } catch (_: Throwable) {
                    // Link loss is handled identically for EOF/protocol/socket errors.
                } finally {
                    close()
                }
            }
        }

        private fun handleFrame(type: Byte, body: ByteArray) {
            when (type) {
                WifiAwareWireProtocol.TYPE_HELLO -> {
                    val remote = WifiAwareWireProtocol.decodeIdentity(body) ?: run {
                        close()
                        return
                    }
                    if (!isCompatible(remote) ||
                        (expectedIdentity != null && expectedIdentity.nodeId != remote.nodeId)
                    ) {
                        close()
                        return
                    }
                    remoteIdentity = remote
                    val existing = links.putIfAbsent(remote.nodeId, this)
                    if (existing != null && existing !== this) {
                        close()
                        return
                    }
                    changeState(TransportState.AVAILABLE)
                    publishMetrics()
                }

                WifiAwareWireProtocol.TYPE_DATA -> {
                    val remote = remoteIdentity ?: return
                    listener?.onEnvelopeReceived(this@WifiAwareTransport, remote.nodeId, body)
                }

                WifiAwareWireProtocol.TYPE_PING -> {
                    if (body.size == 8) {
                        WifiAwareWireProtocol.writeFrame(output, WifiAwareWireProtocol.TYPE_PONG, body)
                    }
                }

                WifiAwareWireProtocol.TYPE_PONG -> {
                    val remote = remoteIdentity ?: return
                    val sentAt = WifiAwareWireProtocol.decodeLong(body) ?: return
                    val rtt = (SystemClock.elapsedRealtime() - sentAt).coerceIn(0L, 60_000L).toInt()
                    lastRttByPeer[remote.nodeId] = rtt
                    publishMetrics()
                }
            }
        }

        fun sendData(envelope: ByteArray): Boolean = try {
            if (closed.get() || remoteIdentity == null) return false
            WifiAwareWireProtocol.writeFrame(output, WifiAwareWireProtocol.TYPE_DATA, envelope)
            true
        } catch (_: Throwable) {
            close()
            false
        }

        fun sendPing(now: Long) {
            try {
                if (!closed.get() && remoteIdentity != null) {
                    WifiAwareWireProtocol.writeFrame(
                        output,
                        WifiAwareWireProtocol.TYPE_PING,
                        WifiAwareWireProtocol.encodeLong(now),
                    )
                }
            } catch (_: Throwable) {
                close()
            }
        }

        fun close() {
            if (!closed.compareAndSet(false, true)) return
            val remoteId = remoteIdentity?.nodeId
            try { socket.close() } catch (_: Throwable) {}
            if (remoteId != null) {
                links.remove(remoteId, this)
                lastRttByPeer.remove(remoteId)
            }
            publishMetrics()
        }
    }

    private fun startHeartbeatLoop() {
        if (heartbeatStarted.compareAndSet(false, true)) {
            heartbeatExecutor.scheduleAtFixedRate({
                if (!started) return@scheduleAtFixedRate
                val now = SystemClock.elapsedRealtime()
                links.values.forEach { it.sendPing(now) }
            }, HEARTBEAT_SECONDS, HEARTBEAT_SECONDS, TimeUnit.SECONDS)
        }
    }

    private fun isCompatible(remote: WifiAwareWireProtocol.Identity): Boolean =
        remote.nodeId != identity.nodeId && remote.rideToken == identity.rideToken

    private fun publishMetrics() {
        val rtts = lastRttByPeer.values
        val averageRtt = if (rtts.isEmpty()) null else rtts.sum() / rtts.size
        listener?.onMetricsChanged(
            this,
            TransportMetrics(
                reachablePeers = links.size,
                estimatedRttMs = averageRtt,
                metered = false,
            ),
        )
    }

    private fun changeState(newState: TransportState) {
        if (state == newState) return
        state = newState
        listener?.onStateChanged(this, newState)
    }

    private fun closeAwareSessions() {
        try { publishSession?.close() } catch (_: Throwable) {}
        try { subscribeSession?.close() } catch (_: Throwable) {}
        try { awareSession?.close() } catch (_: Throwable) {}
        publishSession = null
        subscribeSession = null
        awareSession = null
    }

    private fun closeAllLinks() {
        links.values.toList().forEach { it.close() }
        links.clear()
    }

    private fun closeServer() {
        try { serverSocket?.close() } catch (_: Throwable) {}
        serverSocket = null
    }

    private fun unregisterNetworkCallbacks() {
        val callbacks = synchronized(networkCallbacks) { networkCallbacks.toList() }
        callbacks.forEach { callback ->
            try { connectivityManager.unregisterNetworkCallback(callback) } catch (_: Throwable) {}
        }
        networkCallbacks.clear()
    }

    private fun registerAwareReceiver() {
        if (!receiverRegistered.compareAndSet(false, true)) return
        val filter = IntentFilter(WifiAwareManager.ACTION_WIFI_AWARE_STATE_CHANGED)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            appContext.registerReceiver(awareStateReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("DEPRECATION")
            appContext.registerReceiver(awareStateReceiver, filter)
        }
    }

    private fun unregisterAwareReceiver() {
        if (!receiverRegistered.compareAndSet(true, false)) return
        try { appContext.unregisterReceiver(awareStateReceiver) } catch (_: Throwable) {}
    }

    private fun hasAwarePermission(): Boolean = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        ContextCompat.checkSelfPermission(appContext, Manifest.permission.NEARBY_WIFI_DEVICES) ==
            PackageManager.PERMISSION_GRANTED
    } else {
        ContextCompat.checkSelfPermission(appContext, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
    }

    private fun nextAwareMessageId(): Int = (nextMessageId.getAndIncrement() and 0x7fffffffL).toInt()

    companion object {
        private const val CONNECT_TIMEOUT_MS = 7_000
        private const val HEARTBEAT_SECONDS = 2L
        private val heartbeatStarted = AtomicBoolean(false)
    }
}
