package com.bikemesh.ridemesh.offline

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.net.Uri
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiNetworkSpecifier
import android.os.SystemClock
import com.bikemesh.ridemesh.transport.WifiAwareWireProtocol
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Joins another Android rider's LocalOnlyHotspot and connects to its
 * _ridemesh._tcp Bonjour endpoint using the RMESH1 framed protocol.
 *
 * WifiNetworkSpecifier intentionally uses the Android system approval dialog;
 * RideMesh never silently changes the rider's saved Wi-Fi configuration.
 */
class AndroidHotspotClient(
    context: Context,
    private val nodeId: String,
    private val riderName: String,
    private val rideCode: String,
    private val listener: Listener,
) {
    interface Listener {
        fun onStatus(message: String)
        fun onConnected(nodeId: String, riderName: String)
        fun onDisconnected(nodeId: String?)
        fun onRtt(nodeId: String, rttMs: Int)
        fun onData(nodeId: String, payload: ByteArray)
    }

    private val appContext = context.applicationContext
    private val connectivity = appContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    private val nsd = appContext.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val io = Executors.newCachedThreadPool()
    private val heartbeat: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()
    private val identity = WifiAwareWireProtocol.Identity(
        nodeId = nodeId,
        rideToken = WifiAwareWireProtocol.rideToken(rideCode),
        riderName = riderName.ifBlank { "Rider" },
    )

    @Volatile private var started = false
    @Volatile private var activeNetwork: Network? = null
    @Volatile private var networkCallback: ConnectivityManager.NetworkCallback? = null
    @Volatile private var discoveryListener: NsdManager.DiscoveryListener? = null
    @Volatile private var socket: Socket? = null
    @Volatile private var output: DataOutputStream? = null
    @Volatile private var remoteIdentity: WifiAwareWireProtocol.Identity? = null
    private val connected = AtomicBoolean(false)

    fun start(invitePayload: String) {
        stop()
        val invite = parseInvite(invitePayload) ?: run {
            listener.onStatus("Offline invitation is invalid")
            return
        }
        if (invite.rideToken != identity.rideToken) {
            listener.onStatus("Offline invitation belongs to a different ride")
            return
        }
        started = true
        listener.onStatus("OFFLINE ANDROID CLIENT • requesting direct Wi-Fi join")

        val specifierBuilder = WifiNetworkSpecifier.Builder().setSsid(invite.ssid)
        if (invite.passphrase.isNotBlank()) specifierBuilder.setWpa2Passphrase(invite.passphrase)
        val request = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_WIFI)
            .removeCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .setNetworkSpecifier(specifierBuilder.build())
            .build()

        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                if (!started) return
                activeNetwork = network
                listener.onStatus("OFFLINE DIRECT WI-FI JOINED • discovering RideMesh host")
                startBonjourDiscovery(network)
            }

            override fun onUnavailable() {
                if (started) listener.onStatus("Offline direct Wi-Fi join was not approved or timed out")
            }

            override fun onLost(network: Network) {
                if (activeNetwork == network) {
                    activeNetwork = null
                    closeLink()
                    if (started) listener.onStatus("Offline direct Wi-Fi lost • restart ride to reconnect")
                }
            }
        }
        networkCallback = callback
        try {
            connectivity.requestNetwork(request, callback)
        } catch (t: Throwable) {
            started = false
            listener.onStatus("Offline direct Wi-Fi request failed: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    fun stop() {
        started = false
        stopBonjourDiscovery()
        closeLink()
        networkCallback?.let { runCatching { connectivity.unregisterNetworkCallback(it) } }
        networkCallback = null
        activeNetwork = null
    }

    fun send(payload: ByteArray): Boolean = sendFrame(WifiAwareWireProtocol.TYPE_DATA, payload)

    private fun startBonjourDiscovery(network: Network) {
        stopBonjourDiscovery()
        val discovery = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(serviceType: String) = Unit

            override fun onServiceFound(serviceInfo: NsdServiceInfo) {
                if (!started || connected.get()) return
                if (serviceInfo.serviceType != "_ridemesh._tcp." && serviceInfo.serviceType != "_ridemesh._tcp") return
                if (!serviceInfo.serviceName.contains(identity.rideToken, ignoreCase = true)) return
                resolve(serviceInfo, network)
            }

            override fun onServiceLost(serviceInfo: NsdServiceInfo) = Unit
            override fun onDiscoveryStopped(serviceType: String) = Unit

            override fun onStartDiscoveryFailed(serviceType: String, errorCode: Int) {
                if (started) listener.onStatus("Offline Bonjour discovery failed • $errorCode")
            }

            override fun onStopDiscoveryFailed(serviceType: String, errorCode: Int) = Unit
        }
        discoveryListener = discovery
        try {
            nsd.discoverServices("_ridemesh._tcp.", NsdManager.PROTOCOL_DNS_SD, discovery)
        } catch (t: Throwable) {
            listener.onStatus("Offline Bonjour discovery error: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    @Suppress("DEPRECATION")
    private fun resolve(serviceInfo: NsdServiceInfo, network: Network) {
        runCatching {
            nsd.resolveService(serviceInfo, object : NsdManager.ResolveListener {
                override fun onResolveFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                    if (started) listener.onStatus("Offline RideMesh host resolve failed • $errorCode")
                }

                override fun onServiceResolved(resolved: NsdServiceInfo) {
                    if (!started || connected.get()) return
                    val host = resolved.host ?: return
                    val port = resolved.port.takeIf { it > 0 } ?: WifiAwareWireProtocol.TCP_PORT
                    connectSocket(network, host.hostAddress ?: host.toString(), port)
                }
            })
        }.onFailure {
            if (started) listener.onStatus("Offline RideMesh host resolve error: ${it.message ?: it.javaClass.simpleName}")
        }
    }

    private fun connectSocket(network: Network, host: String, port: Int) {
        if (!connected.compareAndSet(false, true)) return
        io.execute {
            var localSocket: Socket? = null
            try {
                val s = Socket().apply { tcpNoDelay = true }
                localSocket = s
                network.bindSocket(s)
                s.connect(InetSocketAddress(host, port), 8_000)
                if (!started) {
                    s.close()
                    connected.set(false)
                    return@execute
                }
                socket = s
                val input = DataInputStream(s.getInputStream())
                output = DataOutputStream(s.getOutputStream())
                sendFrame(WifiAwareWireProtocol.TYPE_HELLO, WifiAwareWireProtocol.encodeIdentity(identity))
                listener.onStatus("OFFLINE RMESH1 LINK • handshake started")
                startHeartbeat()

                while (started && !s.isClosed) {
                    val frame = WifiAwareWireProtocol.readFrame(input) ?: break
                    handleFrame(frame.first, frame.second)
                }
            } catch (t: Throwable) {
                if (started) listener.onStatus("Offline RMESH1 connection failed: ${t.message ?: t.javaClass.simpleName}")
            } finally {
                val remote = remoteIdentity
                remoteIdentity = null
                output = null
                runCatching { localSocket?.close() }
                if (socket === localSocket) socket = null
                connected.set(false)
                if (remote != null) listener.onDisconnected(remote.nodeId)
            }
        }
    }

    private fun handleFrame(type: Byte, body: ByteArray) {
        when (type) {
            WifiAwareWireProtocol.TYPE_HELLO -> {
                val remote = WifiAwareWireProtocol.decodeIdentity(body) ?: return
                if (remote.rideToken != identity.rideToken || remote.nodeId == identity.nodeId) {
                    closeLink()
                    return
                }
                remoteIdentity = remote
                listener.onConnected(remote.nodeId, remote.riderName)
                listener.onStatus("OFFLINE CONNECTED • ${remote.riderName}")
            }

            WifiAwareWireProtocol.TYPE_DATA -> remoteIdentity?.let { listener.onData(it.nodeId, body) }
            WifiAwareWireProtocol.TYPE_PING -> if (body.size == 8) sendFrame(WifiAwareWireProtocol.TYPE_PONG, body)
            WifiAwareWireProtocol.TYPE_PONG -> {
                val sent = WifiAwareWireProtocol.decodeLong(body) ?: return
                val rtt = (SystemClock.elapsedRealtime() - sent).coerceIn(0L, 60_000L).toInt()
                remoteIdentity?.let { listener.onRtt(it.nodeId, rtt) }
            }
        }
    }

    private fun startHeartbeat() {
        heartbeat.scheduleAtFixedRate({
            if (!started || !connected.get()) return@scheduleAtFixedRate
            sendFrame(WifiAwareWireProtocol.TYPE_PING, WifiAwareWireProtocol.encodeLong(SystemClock.elapsedRealtime()))
        }, 2, 2, TimeUnit.SECONDS)
    }

    private fun sendFrame(type: Byte, body: ByteArray): Boolean {
        val stream = output ?: return false
        return synchronized(stream) {
            try {
                WifiAwareWireProtocol.writeFrame(stream, type, body)
                true
            } catch (_: Throwable) {
                closeLink()
                false
            }
        }
    }

    private fun closeLink() {
        val remote = remoteIdentity
        remoteIdentity = null
        output = null
        runCatching { socket?.close() }
        socket = null
        connected.set(false)
        if (remote != null) listener.onDisconnected(remote.nodeId)
    }

    private fun stopBonjourDiscovery() {
        val discovery = discoveryListener ?: return
        discoveryListener = null
        runCatching { nsd.stopServiceDiscovery(discovery) }
    }

    private data class Invite(
        val ssid: String,
        val passphrase: String,
        val rideToken: String,
    )

    private fun parseInvite(payload: String): Invite? {
        return runCatching {
            val uri = Uri.parse(payload)
            if (uri.scheme != "ridemesh" || uri.host != "offline") return null
            val ssid = uri.getQueryParameter("ssid")?.takeIf { it.isNotBlank() } ?: return null
            val pass = uri.getQueryParameter("pass").orEmpty()
            val token = uri.getQueryParameter("token")?.takeIf { it.isNotBlank() } ?: return null
            Invite(ssid, pass, token)
        }.getOrNull()
    }
}
