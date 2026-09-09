package com.bikemesh.ridemesh.offline

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import androidx.core.content.ContextCompat
import com.bikemesh.ridemesh.transport.WifiAwareWireProtocol
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.ServerSocket
import java.net.Socket
import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Cross-platform offline fallback for Android <-> iPhone.
 *
 * Android owns a LocalOnlyHotspot (no Internet), advertises a Bonjour/DNS-SD
 * _ridemesh._tcp service on TCP 49355, and speaks the exact same RMESH1 framed
 * protocol as WifiAwareTransport. The iOS test app joins the hotspot with
 * NEHotspotConfigurationManager, discovers the service with NWBrowser, then
 * connects with NWConnection.
 */
class LocalHotspotHost(
    context: Context,
    private val nodeId: String,
    private val riderName: String,
    rideCode: String,
    private val listener: Listener,
) {
    interface Listener {
        fun onStatus(message: String)
        fun onHotspotReady(ssid: String, passphrase: String?, invitePayload: String)
        fun onPeerConnected(nodeId: String, riderName: String)
        fun onPeerDisconnected(nodeId: String)
        fun onRtt(nodeId: String, rttMs: Int)
        fun onData(nodeId: String, payload: ByteArray)
    }

    private val appContext = context.applicationContext
    private val wifiManager = appContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val nsdManager = appContext.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val mainHandler = Handler(Looper.getMainLooper())
    private val ioExecutor = Executors.newCachedThreadPool()
    private val heartbeatExecutor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
    private val identity = WifiAwareWireProtocol.Identity(
        nodeId = nodeId,
        rideToken = WifiAwareWireProtocol.rideToken(rideCode),
        riderName = riderName.ifBlank { "Rider" },
    )
    private val rideCodeNormalized = rideCode.trim().uppercase()
    private val links = ConcurrentHashMap<String, PeerLink>()

    @Volatile private var started = false
    @Volatile private var reservation: WifiManager.LocalOnlyHotspotReservation? = null
    @Volatile private var serverSocket: ServerSocket? = null
    @Volatile private var registrationListener: NsdManager.RegistrationListener? = null
    @Volatile private var currentInvitePayload: String? = null
    @Volatile private var currentSsid: String? = null
    @Volatile private var currentPassphrase: String? = null

    fun start() {
        if (started) return
        started = true
        listener.onStatus("Offline local link: starting Android hotspot")

        if (!hasPermission()) {
            listener.onStatus("Offline local link unavailable: nearby Wi-Fi permission missing")
            return
        }

        try {
            wifiManager.startLocalOnlyHotspot(object : WifiManager.LocalOnlyHotspotCallback() {
                override fun onStarted(reservation: WifiManager.LocalOnlyHotspotReservation) {
                    if (!started) {
                        reservation.close()
                        return
                    }
                    this@LocalHotspotHost.reservation = reservation
                    val credentials = readCredentials(reservation)
                    if (credentials == null) {
                        listener.onStatus("Offline hotspot started but Android did not expose usable credentials")
                        return
                    }
                    val (ssid, passphrase) = credentials
                    currentSsid = ssid
                    currentPassphrase = passphrase
                    val payload = buildInvitePayload(ssid, passphrase)
                    currentInvitePayload = payload
                    startServer()
                    registerBonjour()
                    listener.onHotspotReady(ssid, passphrase, payload)
                    listener.onStatus("OFFLINE HOTSPOT READY • Invite iPhone with QR")
                }

                override fun onStopped() {
                    reservation = null
                    currentInvitePayload = null
                    if (started) listener.onStatus("Offline hotspot stopped by Android")
                    closeServerAndLinks()
                    unregisterBonjour()
                }

                override fun onFailed(reason: Int) {
                    reservation = null
                    listener.onStatus("Offline hotspot failed • code $reason")
                    closeServerAndLinks()
                    unregisterBonjour()
                }
            }, mainHandler)
        } catch (security: SecurityException) {
            listener.onStatus("Offline hotspot permission error")
        } catch (t: Throwable) {
            listener.onStatus("Offline hotspot error: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    fun stop() {
        if (!started) return
        started = false
        unregisterBonjour()
        closeServerAndLinks()
        runCatching { reservation?.close() }
        reservation = null
        currentInvitePayload = null
        currentSsid = null
        currentPassphrase = null
    }

    fun invitePayload(): String? = currentInvitePayload

    fun hotspotSummary(): String? {
        val ssid = currentSsid ?: return null
        val pass = currentPassphrase
        return if (pass.isNullOrBlank()) "SSID: $ssid • OPEN" else "SSID: $ssid • Password: $pass"
    }

    fun connectedPeerCount(): Int = links.size

    fun connectedPeers(): List<Pair<String, String>> = links.values.mapNotNull { link ->
        link.remoteIdentity?.let { it.nodeId to it.riderName }
    }

    fun send(payload: ByteArray, destinationNodeId: String? = null): Boolean {
        return if (destinationNodeId != null) {
            links[destinationNodeId]?.sendData(payload) == true
        } else {
            var sent = false
            links.values.forEach { sent = it.sendData(payload) || sent }
            sent
        }
    }

    private fun hasPermission(): Boolean {
        val permission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.NEARBY_WIFI_DEVICES
        } else {
            Manifest.permission.ACCESS_FINE_LOCATION
        }
        return ContextCompat.checkSelfPermission(appContext, permission) == PackageManager.PERMISSION_GRANTED
    }

    @Suppress("DEPRECATION")
    private fun readCredentials(reservation: WifiManager.LocalOnlyHotspotReservation): Pair<String, String?>? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val config = reservation.softApConfiguration
            val ssid = config.ssid?.trim()?.takeIf { it.isNotBlank() } ?: return null
            ssid to config.passphrase
        } else {
            val config = reservation.wifiConfiguration ?: return null
            val ssid = config.SSID?.trim('"')?.takeIf { it.isNotBlank() } ?: return null
            ssid to config.preSharedKey?.trim('"')
        }
    }

    private fun buildInvitePayload(ssid: String, passphrase: String?): String {
        fun enc(value: String): String = URLEncoder.encode(value, StandardCharsets.UTF_8.name())
        val pass = passphrase.orEmpty()
        return "ridemesh://offline?ssid=${enc(ssid)}&pass=${enc(pass)}&ride=${enc(rideCodeNormalized)}&token=${enc(identity.rideToken)}"
    }

    private fun startServer() {
        if (serverSocket?.isClosed == false) return
        try {
            val server = ServerSocket(WifiAwareWireProtocol.TCP_PORT).apply { reuseAddress = true }
            serverSocket = server
            ioExecutor.execute {
                while (started && !server.isClosed) {
                    try {
                        val socket = server.accept().apply { tcpNoDelay = true }
                        PeerLink(socket).start()
                    } catch (_: Throwable) {
                        if (!started || server.isClosed) break
                    }
                }
            }
            startHeartbeatLoop()
        } catch (t: Throwable) {
            listener.onStatus("Offline TCP server failed: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    private fun registerBonjour() {
        unregisterBonjour()
        val serviceInfo = NsdServiceInfo().apply {
            serviceName = "RideMesh-${identity.rideToken}-${nodeId.take(8)}"
            serviceType = "_ridemesh._tcp."
            port = WifiAwareWireProtocol.TCP_PORT
            runCatching { setAttribute("ride", identity.rideToken) }
            runCatching { setAttribute("name", identity.riderName) }
            runCatching { setAttribute("protocol", WifiAwareWireProtocol.PROTOCOL_VERSION.toString()) }
        }
        val registration = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(serviceInfo: NsdServiceInfo) {
                listener.onStatus("Offline Bonjour ready • ${serviceInfo.serviceName}")
            }

            override fun onRegistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                listener.onStatus("Offline Bonjour registration failed • $errorCode")
            }

            override fun onServiceUnregistered(serviceInfo: NsdServiceInfo) = Unit
            override fun onUnregistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = Unit
        }
        registrationListener = registration
        try {
            nsdManager.registerService(serviceInfo, NsdManager.PROTOCOL_DNS_SD, registration)
        } catch (t: Throwable) {
            registrationListener = null
            listener.onStatus("Offline Bonjour error: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    private fun unregisterBonjour() {
        val registration = registrationListener ?: return
        registrationListener = null
        runCatching { nsdManager.unregisterService(registration) }
    }

    private fun startHeartbeatLoop() {
        heartbeatExecutor.scheduleAtFixedRate({
            if (!started) return@scheduleAtFixedRate
            val nowMs = android.os.SystemClock.elapsedRealtime()
            val body = WifiAwareWireProtocol.encodeLong(nowMs)
            links.values.forEach { it.sendFrame(WifiAwareWireProtocol.TYPE_PING, body) }
        }, 2, 2, TimeUnit.SECONDS)
    }

    private fun closeServerAndLinks() {
        val peers = links.values.toList()
        links.clear()
        peers.forEach { it.close() }
        runCatching { serverSocket?.close() }
        serverSocket = null
    }

    private inner class PeerLink(private val socket: Socket) {
        private val closed = AtomicBoolean(false)
        private val input = DataInputStream(socket.getInputStream())
        private val output = DataOutputStream(socket.getOutputStream())

        @Volatile var remoteIdentity: WifiAwareWireProtocol.Identity? = null
            private set

        fun start() {
            if (!sendFrame(WifiAwareWireProtocol.TYPE_HELLO, WifiAwareWireProtocol.encodeIdentity(identity))) {
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
                    // EOF/socket/protocol errors all terminate the same link.
                } finally {
                    close()
                }
            }
        }

        private fun handleFrame(type: Byte, body: ByteArray) {
            when (type) {
                WifiAwareWireProtocol.TYPE_HELLO -> {
                    val remote = WifiAwareWireProtocol.decodeIdentity(body) ?: run { close(); return }
                    if (remote.rideToken != identity.rideToken || remote.nodeId == identity.nodeId) {
                        close()
                        return
                    }
                    remoteIdentity = remote
                    val previous = links.put(remote.nodeId, this)
                    if (previous != null && previous !== this) previous.close()
                    listener.onPeerConnected(remote.nodeId, remote.riderName)
                    listener.onStatus("OFFLINE CONNECTED • ${remote.riderName}")
                }

                WifiAwareWireProtocol.TYPE_DATA -> {
                    remoteIdentity?.let { listener.onData(it.nodeId, body) }
                }

                WifiAwareWireProtocol.TYPE_PING -> {
                    if (body.size == 8) sendFrame(WifiAwareWireProtocol.TYPE_PONG, body)
                }

                WifiAwareWireProtocol.TYPE_PONG -> {
                    val sent = WifiAwareWireProtocol.decodeLong(body) ?: return
                    val now = android.os.SystemClock.elapsedRealtime()
                    val rtt = (now - sent).coerceIn(0L, 60_000L).toInt()
                    remoteIdentity?.let { listener.onRtt(it.nodeId, rtt) }
                }
            }
        }

        fun sendData(payload: ByteArray): Boolean = sendFrame(WifiAwareWireProtocol.TYPE_DATA, payload)

        fun sendFrame(type: Byte, body: ByteArray): Boolean {
            if (closed.get()) return false
            return try {
                WifiAwareWireProtocol.writeFrame(output, type, body)
                true
            } catch (_: Throwable) {
                close()
                false
            }
        }

        fun close() {
            if (!closed.compareAndSet(false, true)) return
            val remote = remoteIdentity
            if (remote != null) {
                links.remove(remote.nodeId, this)
                listener.onPeerDisconnected(remote.nodeId)
                listener.onStatus("Offline peer disconnected • reconnecting")
            }
            runCatching { socket.close() }
        }
    }
}
