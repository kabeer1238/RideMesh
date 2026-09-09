package com.bikemesh.ridemesh.offline

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.SoftApConfiguration
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import com.bikemesh.ridemesh.transport.WifiAwareWireProtocol
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Cross-platform fallback transport for Android <-> iPhone when raw Wi-Fi Aware
 * pairing is unavailable or unreliable. Android owns a LocalOnlyHotspot, advertises
 * RideMesh over Bonjour/DNS-SD, and accepts the same RMESH1 framed TCP protocol
 * used by WifiAwareTransport.
 */
class LocalHotspotBridge(
    context: Context,
    private val identity: WifiAwareWireProtocol.Identity,
    private val onStatus: (String) -> Unit,
    private val onCredentials: (ssid: String, passphrase: String) -> Unit,
    private val onPeerChanged: (name: String?, rttMs: Int?) -> Unit,
) {
    private val appContext = context.applicationContext
    private val wifiManager = appContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val nsdManager = appContext.getSystemService(Context.NSD_SERVICE) as NsdManager
    private val handler = Handler(Looper.getMainLooper())
    private val io = Executors.newCachedThreadPool()
    private val heartbeat: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor()

    @Volatile private var reservation: WifiManager.LocalOnlyHotspotReservation? = null
    @Volatile private var server: ServerSocket? = null
    @Volatile private var activeLink: PeerLink? = null
    @Volatile private var registration: NsdManager.RegistrationListener? = null
    @Volatile private var started = false

    fun start() {
        if (started) return
        started = true
        onStatus("Offline fallback: starting local-only Wi-Fi")
        try {
            wifiManager.startLocalOnlyHotspot(object : WifiManager.LocalOnlyHotspotCallback() {
                override fun onStarted(res: WifiManager.LocalOnlyHotspotReservation) {
                    if (!started) {
                        res.close()
                        return
                    }
                    reservation = res
                    val credentials = hotspotCredentials(res)
                    if (credentials == null) {
                        onStatus("Offline fallback: hotspot started but credentials unavailable")
                        return
                    }
                    onCredentials(credentials.first, credentials.second)
                    onStatus("Offline fallback: hotspot ready • ${credentials.first}")
                    startServerAndBonjour()
                }

                override fun onStopped() {
                    onStatus("Offline fallback: hotspot stopped")
                    stopNetworkOnly()
                }

                override fun onFailed(reason: Int) {
                    onStatus("Offline fallback: hotspot failed ($reason)")
                }
            }, handler)
        } catch (t: Throwable) {
            onStatus("Offline fallback unavailable: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    fun stop() {
        started = false
        activeLink?.close()
        activeLink = null
        stopNetworkOnly()
        runCatching { reservation?.close() }
        reservation = null
        onPeerChanged(null, null)
    }

    private fun hotspotCredentials(res: WifiManager.LocalOnlyHotspotReservation): Pair<String, String>? {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val c: SoftApConfiguration = res.softApConfiguration
            val ssid = c.ssid ?: return null
            val pass = c.passphrase.orEmpty()
            ssid to pass
        } else {
            @Suppress("DEPRECATION") val c = res.wifiConfiguration ?: return null
            @Suppress("DEPRECATION") val ssid = c.SSID ?: return null
            @Suppress("DEPRECATION") val pass = c.preSharedKey.orEmpty()
            ssid.trim('"') to pass.trim('"')
        }
    }

    private fun startServerAndBonjour() {
        if (!started || server?.isClosed == false) return
        try {
            val socket = ServerSocket(WifiAwareWireProtocol.TCP_PORT)
            socket.reuseAddress = true
            server = socket
            registerBonjour()
            io.execute {
                while (started && !socket.isClosed) {
                    try {
                        val peer = socket.accept().apply { tcpNoDelay = true }
                        activeLink?.close()
                        PeerLink(peer).also {
                            activeLink = it
                            it.start()
                        }
                    } catch (_: Throwable) {
                        if (!started || socket.isClosed) break
                    }
                }
            }
            heartbeat.scheduleAtFixedRate({ activeLink?.sendPing() }, 2, 2, TimeUnit.SECONDS)
        } catch (t: Throwable) {
            onStatus("Offline fallback TCP failed: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    private fun registerBonjour() {
        val service = NsdServiceInfo().apply {
            serviceName = "RideMesh-${identity.nodeId.take(8)}"
            serviceType = "_ridemesh._tcp."
            port = WifiAwareWireProtocol.TCP_PORT
            setAttribute("ride", identity.rideToken)
            setAttribute("node", identity.nodeId.take(32))
        }
        val listener = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(serviceInfo: NsdServiceInfo) {
                onStatus("Offline fallback: Bonjour ready • ${serviceInfo.serviceName}")
            }
            override fun onRegistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                onStatus("Offline fallback: Bonjour registration failed ($errorCode)")
            }
            override fun onServiceUnregistered(serviceInfo: NsdServiceInfo) = Unit
            override fun onUnregistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) = Unit
        }
        registration = listener
        nsdManager.registerService(service, NsdManager.PROTOCOL_DNS_SD, listener)
    }

    private fun stopNetworkOnly() {
        registration?.let { runCatching { nsdManager.unregisterService(it) } }
        registration = null
        runCatching { server?.close() }
        server = null
    }

    private inner class PeerLink(private val socket: Socket) {
        private val closed = AtomicBoolean(false)
        private val input = DataInputStream(socket.getInputStream())
        private val output = DataOutputStream(socket.getOutputStream())
        @Volatile private var remote: WifiAwareWireProtocol.Identity? = null

        fun start() {
            runCatching {
                WifiAwareWireProtocol.writeFrame(output, WifiAwareWireProtocol.TYPE_HELLO, WifiAwareWireProtocol.encodeIdentity(identity))
            }.onFailure { close(); return }
            io.execute {
                try {
                    while (!closed.get()) {
                        val frame = WifiAwareWireProtocol.readFrame(input) ?: break
                        when (frame.first) {
                            WifiAwareWireProtocol.TYPE_HELLO -> {
                                val peer = WifiAwareWireProtocol.decodeIdentity(frame.second) ?: break
                                if (peer.rideToken != identity.rideToken) break
                                remote = peer
                                onStatus("OFFLINE CONNECTED • ${peer.riderName}")
                                onPeerChanged(peer.riderName, null)
                            }
                            WifiAwareWireProtocol.TYPE_PING -> if (frame.second.size == 8) {
                                WifiAwareWireProtocol.writeFrame(output, WifiAwareWireProtocol.TYPE_PONG, frame.second)
                            }
                            WifiAwareWireProtocol.TYPE_PONG -> {
                                val sent = WifiAwareWireProtocol.decodeLong(frame.second) ?: continue
                                val rtt = (SystemClock.elapsedRealtime() - sent).coerceAtLeast(0).toInt()
                                onPeerChanged(remote?.riderName, rtt)
                            }
                        }
                    }
                } catch (_: Throwable) {
                } finally {
                    close()
                }
            }
        }

        fun sendPing() {
            if (closed.get() || remote == null) return
            runCatching {
                WifiAwareWireProtocol.writeFrame(
                    output,
                    WifiAwareWireProtocol.TYPE_PING,
                    WifiAwareWireProtocol.encodeLong(SystemClock.elapsedRealtime()),
                )
            }.onFailure { close() }
        }

        fun close() {
            if (!closed.compareAndSet(false, true)) return
            runCatching { socket.close() }
            if (activeLink === this) activeLink = null
            onPeerChanged(null, null)
            onStatus("Offline fallback: peer disconnected")
        }
    }
}
