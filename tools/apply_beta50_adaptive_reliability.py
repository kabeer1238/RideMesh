from pathlib import Path
import re

ROOT = Path('.')

internet = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt'
s = internet.read_text()

# -----------------------------------------------------------------------------
# Beta5.0 / vc18 reliability pass.
# Keep the vc17 media path and public black-box UI, while adding:
#   - measured per-rider quality (loss / RTT / jitter)
#   - conservative adaptive Opus bitrate tiers (FEC stays enabled)
#   - Bluetooth communication-route self-healing
#   - explicit default-network handover recovery
# -----------------------------------------------------------------------------

# Android recovery imports.
imports = {
    'import android.media.AudioDeviceInfo\n': 'import android.media.AudioDeviceInfo\nimport android.media.AudioDeviceCallback\n',
    'import android.os.Build\n': 'import android.os.Build\nimport android.os.Handler\nimport android.os.Looper\n',
    'import android.content.Context\n': 'import android.content.Context\nimport android.net.ConnectivityManager\nimport android.net.Network\nimport android.net.NetworkCapabilities\n',
}
for old, new in imports.items():
    if new not in s:
        if old not in s:
            raise SystemExit(f'import anchor missing: {old.strip()}')
        s = s.replace(old, new, 1)

# Public rider model gets a rider-friendly quality label.  No transport metrics are
# exposed to normal UI; engineering numbers remain internal only.
old_rider = '''    data class RiderPeer(
        val id: UUID,
        val riderName: String,
        val deviceName: String,
        val lastSeenMs: Long,
        val qualityBars: Int = 4,
    ) {
'''
new_rider = '''    data class RiderPeer(
        val id: UUID,
        val riderName: String,
        val deviceName: String,
        val lastSeenMs: Long,
        val qualityBars: Int = 4,
        val qualityLabel: String = "Good",
    ) {
'''
if 'val qualityLabel: String = "Good"' not in s:
    if old_rider not in s:
        raise SystemExit('RiderPeer anchor not found')
    s = s.replace(old_rider, new_rider, 1)

# Peer session stores only rolling health state needed for adaptive behavior.
old_session_tail = '''        @Volatile var lastStateChangeMs: Long = System.currentTimeMillis(),
        @Volatile var reconnectScheduled: Boolean = false,
    )
'''
new_session_tail = '''        @Volatile var lastStateChangeMs: Long = System.currentTimeMillis(),
        @Volatile var reconnectScheduled: Boolean = false,
        @Volatile var measuredQualityBars: Int = 3,
        @Volatile var measuredQualityLabel: String = "Good",
        @Volatile var lastRttMs: Double = -1.0,
        @Volatile var lastJitterMs: Double = -1.0,
        @Volatile var lastLossPercent: Double = -1.0,
        @Volatile var lastPacketsLost: Long = -1L,
        @Volatile var lastPacketsReceived: Long = -1L,
        @Volatile var audioQualityTier: Int = 0,
    )
'''
if 'measuredQualityLabel' not in s:
    if old_session_tail not in s:
        raise SystemExit('PeerSession tail anchor not found')
    s = s.replace(old_session_tail, new_session_tail, 1)

# Runtime monitor/callback state.
atomic_anchor = '    private val reconnects = AtomicInteger(0)\n'
if 'healthStatsPending' not in s:
    if atomic_anchor not in s:
        raise SystemExit('atomic state anchor not found')
    s = s.replace(
        atomic_anchor,
        atomic_anchor
        + '    private val healthStatsPending = ConcurrentHashMap.newKeySet<UUID>()\n',
        1,
    )

state_anchor = '    @Volatile private var audioStatus = "WEBRTC AUDIO READY"\n'
if 'connectionHealthThread' not in s:
    if state_anchor not in s:
        raise SystemExit('runtime state anchor not found')
    s = s.replace(
        state_anchor,
        state_anchor
        + '    @Volatile private var connectionHealthThread: Thread? = null\n'
        + '    @Volatile private var networkHandoverPending = false\n'
        + '    @Volatile private var lastNetworkHandle = -1L\n'
        + '    @Volatile private var lastNetworkTransport = ""\n',
        1,
    )

manager_anchor = '    private var audioFocusRequest: AudioFocusRequest? = null\n'
if 'audioDeviceCallback' not in s:
    if manager_anchor not in s:
        raise SystemExit('manager state anchor not found')
    s = s.replace(
        manager_anchor,
        manager_anchor
        + '    private var recoveryHandler: Handler? = null\n'
        + '    private var audioDeviceCallback: AudioDeviceCallback? = null\n'
        + '    private var connectivityManager: ConnectivityManager? = null\n'
        + '    private var networkCallback: ConnectivityManager.NetworkCallback? = null\n',
        1,
    )

# Register recovery callbacks and health monitoring only while a ride is active.
start_old = '''        requestAudioFocus()
        selectAudioRoute()
        applyVoiceEnabled()
        startSmartDucking()

        listener.onInternetState(false, "WEBRTC SIGNALING CONNECTING • OPUS VOICE")
'''
start_new = '''        requestAudioFocus()
        selectAudioRoute()
        applyVoiceEnabled()
        registerRecoveryCallbacks(ctx)
        startSmartDucking()
        startConnectionHealthMonitor()

        listener.onInternetState(false, "WEBRTC SIGNALING CONNECTING • OPUS VOICE")
'''
if 'registerRecoveryCallbacks(ctx)' not in s:
    if start_old not in s:
        raise SystemExit('vc17 ride-start anchor not found')
    s = s.replace(start_old, start_new, 1)

stop_old = '''        stopSmartDucking(restoreVolume = true)
        abandonAudioFocus()
        clearCommunicationRoute()
'''
stop_new = '''        stopConnectionHealthMonitor()
        unregisterRecoveryCallbacks()
        stopSmartDucking(restoreVolume = true)
        abandonAudioFocus()
        clearCommunicationRoute()
'''
if 'unregisterRecoveryCallbacks()' not in s:
    if stop_old not in s:
        raise SystemExit('vc17 ride-stop anchor not found')
    s = s.replace(stop_old, stop_new, 1)

# Use real measured quality in the public RiderPeer model.
old_remote = '''    fun remotePeers(): List<RiderPeer> = peers.values
        .map { peer -> peer.copy(qualityBars = qualityBarsFor(peer.id)) }
        .sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName })
'''
new_remote = '''    fun remotePeers(): List<RiderPeer> = peers.values
        .map { peer ->
            peer.copy(
                qualityBars = qualityBarsFor(peer.id),
                qualityLabel = qualityLabelFor(peer.id),
            )
        }
        .sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName })
'''
if 'qualityLabel = qualityLabelFor(peer.id)' not in s:
    if old_remote not in s:
        raise SystemExit('remotePeers anchor not found')
    s = s.replace(old_remote, new_remote, 1)

# New presence copies the current measured public label if a session already exists.
old_presence = '''            lastSeenMs = now,
            qualityBars = qualityBarsFor(presence.origin),
        )
'''
new_presence = '''            lastSeenMs = now,
            qualityBars = qualityBarsFor(presence.origin),
            qualityLabel = qualityLabelFor(presence.origin),
        )
'''
if 'qualityLabel = qualityLabelFor(presence.origin)' not in s:
    if old_presence not in s:
        raise SystemExit('presence rider-model anchor not found')
    s = s.replace(old_presence, new_presence, 1)

# Replace the old connection-state-only bars with measured quality + reconnecting label.
quality_pattern = re.compile(
    r'    private fun qualityBarsFor\(id: UUID\): Int \{.*?\n    \}\n\n    private fun connectionLoop',
    re.S,
)
quality_replacement = r'''    private fun qualityBarsFor(id: UUID): Int {
        val session = sessions[id] ?: return 2
        if (!session.connected) return 1
        return session.measuredQualityBars.coerceIn(1, 4)
    }

    private fun qualityLabelFor(id: UUID): String {
        val session = sessions[id] ?: return "Connecting"
        if (!session.connected) return "Reconnecting"
        return session.measuredQualityLabel.ifBlank { "Good" }
    }

    private fun connectionLoop'''
s, count = quality_pattern.subn(quality_replacement, s, count=1)
if count != 1:
    raise SystemExit('qualityBarsFor block not found')

# After signaling reconnects on a changed default network, immediately restart ICE
# from the deterministic initiator side.  This keeps the same room/rider identity.
connect_anchor = '''        listener.onInternetState(true, "WEBRTC SIGNALING READY • OPUS VOICE")
        publishPresence()

        var lastPing = System.currentTimeMillis()
'''
connect_replacement = '''        listener.onInternetState(true, "WEBRTC SIGNALING READY • OPUS VOICE")
        publishPresence()
        if (networkHandoverPending) {
            networkHandoverPending = false
            recoverPeersAfterNetworkHandover()
        }

        var lastPing = System.currentTimeMillis()
'''
if 'recoverPeersAfterNetworkHandover()' not in s:
    if connect_anchor not in s:
        raise SystemExit('signaling ready anchor not found')
    s = s.replace(connect_anchor, connect_replacement, 1)

# Mark public state immediately when a peer drops/reconnects.
mark_anchor = '''        session.connected = connected
        session.state = state
        session.lastStateChangeMs = System.currentTimeMillis()
'''
mark_replacement = '''        session.connected = connected
        session.state = state
        session.lastStateChangeMs = System.currentTimeMillis()
        if (!connected) {
            session.measuredQualityBars = 1
            session.measuredQualityLabel = "Reconnecting"
        } else if (session.measuredQualityLabel == "Reconnecting") {
            session.measuredQualityBars = 3
            session.measuredQualityLabel = "Good"
        }
'''
if 'session.measuredQualityLabel = "Reconnecting"' not in s:
    if mark_anchor not in s:
        raise SystemExit('markPeerConnected anchor not found')
    s = s.replace(mark_anchor, mark_replacement, 1)

# Insert adaptive health, Bluetooth route recovery, and network handover helpers.
insert_anchor = '    private fun connectionLoop() {\n'
if 'private fun startConnectionHealthMonitor()' not in s:
    helpers = r'''    private fun startConnectionHealthMonitor() {
        stopConnectionHealthMonitor()
        healthStatsPending.clear()
        connectionHealthThread = Thread({
            try {
                while (running.get() && !Thread.currentThread().isInterrupted) {
                    val snapshot = sessions.values.toList()
                    snapshot.forEach { session ->
                        if (session.connected) collectPeerHealth(session)
                    }
                    Thread.sleep(CONNECTION_HEALTH_POLL_MS)
                }
            } catch (_: InterruptedException) {
                // Ride stopped/restarted.
            }
        }, "RideMesh-ConnectionHealth").apply {
            isDaemon = true
            start()
        }
    }

    private fun stopConnectionHealthMonitor() {
        connectionHealthThread?.interrupt()
        connectionHealthThread = null
        healthStatsPending.clear()
    }

    private fun collectPeerHealth(session: PeerSession) {
        if (!healthStatsPending.add(session.id)) return
        runCatching {
            session.pc.getStats { report ->
                try {
                    var rttMs = -1.0
                    var jitterMs = -1.0
                    var packetsLost = -1L
                    var packetsReceived = -1L

                    report.statsMap.values.forEach { stat ->
                        val members = stat.members
                        when (stat.type) {
                            "candidate-pair" -> {
                                val state = members["state"]?.toString().orEmpty()
                                val nominated = members["nominated"] as? Boolean ?: false
                                if ((state.equals("succeeded", true) || nominated) && rttMs < 0.0) {
                                    val seconds = (members["currentRoundTripTime"] as? Number)?.toDouble()
                                    if (seconds != null && seconds >= 0.0) rttMs = seconds * 1000.0
                                }
                            }

                            "remote-inbound-rtp" -> {
                                val kind = (members["kind"] ?: members["mediaType"])?.toString().orEmpty()
                                if (kind.equals("audio", true) && rttMs < 0.0) {
                                    val seconds = (members["roundTripTime"] as? Number)?.toDouble()
                                    if (seconds != null && seconds >= 0.0) rttMs = seconds * 1000.0
                                }
                            }

                            "inbound-rtp" -> {
                                val kind = (members["kind"] ?: members["mediaType"])?.toString().orEmpty()
                                if (!kind.equals("audio", true)) return@forEach
                                val jitterSeconds = (members["jitter"] as? Number)?.toDouble()
                                if (jitterSeconds != null && jitterSeconds >= 0.0) {
                                    jitterMs = maxOf(jitterMs, jitterSeconds * 1000.0)
                                }
                                val lost = (members["packetsLost"] as? Number)?.toLong()
                                val received = (members["packetsReceived"] as? Number)?.toLong()
                                if (lost != null) packetsLost = maxOf(packetsLost, lost)
                                if (received != null) packetsReceived = maxOf(packetsReceived, received)
                            }
                        }
                    }

                    val lossPercent = calculateLossPercent(session, packetsLost, packetsReceived)
                    updateMeasuredQuality(session, rttMs, jitterMs, lossPercent)
                } finally {
                    healthStatsPending.remove(session.id)
                }
            }
        }.onFailure {
            healthStatsPending.remove(session.id)
        }
    }

    private fun calculateLossPercent(session: PeerSession, lost: Long, received: Long): Double {
        if (lost < 0L || received < 0L) return session.lastLossPercent
        val previousLost = session.lastPacketsLost
        val previousReceived = session.lastPacketsReceived
        session.lastPacketsLost = lost
        session.lastPacketsReceived = received

        val lostDelta = if (previousLost >= 0L && lost >= previousLost) lost - previousLost else lost
        val receivedDelta = if (previousReceived >= 0L && received >= previousReceived) {
            received - previousReceived
        } else {
            received
        }
        val total = lostDelta + receivedDelta
        if (total <= 0L) return session.lastLossPercent
        return (lostDelta.coerceAtLeast(0L).toDouble() * 100.0 / total.toDouble()).coerceIn(0.0, 100.0)
    }

    private fun updateMeasuredQuality(
        session: PeerSession,
        rttMs: Double,
        jitterMs: Double,
        lossPercent: Double,
    ) {
        if (!session.connected) return
        if (rttMs >= 0.0) session.lastRttMs = rttMs
        if (jitterMs >= 0.0) session.lastJitterMs = jitterMs
        if (lossPercent >= 0.0) session.lastLossPercent = lossPercent

        val rtt = session.lastRttMs
        val jitter = session.lastJitterMs
        val loss = session.lastLossPercent

        val poor = (loss >= QUALITY_POOR_LOSS_PERCENT) ||
            (rtt >= QUALITY_POOR_RTT_MS) ||
            (jitter >= QUALITY_POOR_JITTER_MS)
        val excellent = !poor &&
            (loss < 0.0 || loss <= QUALITY_EXCELLENT_LOSS_PERCENT) &&
            (rtt < 0.0 || rtt <= QUALITY_EXCELLENT_RTT_MS) &&
            (jitter < 0.0 || jitter <= QUALITY_EXCELLENT_JITTER_MS)

        when {
            poor -> {
                session.measuredQualityBars = 1
                session.measuredQualityLabel = "Poor"
                applyAdaptiveAudioTier(session, AUDIO_TIER_POOR)
            }
            excellent -> {
                session.measuredQualityBars = 4
                session.measuredQualityLabel = "Excellent"
                applyAdaptiveAudioTier(session, AUDIO_TIER_EXCELLENT)
            }
            else -> {
                session.measuredQualityBars = 3
                session.measuredQualityLabel = "Good"
                applyAdaptiveAudioTier(session, AUDIO_TIER_GOOD)
            }
        }

        peers.computeIfPresent(session.id) { _, peer ->
            peer.copy(
                qualityBars = session.measuredQualityBars,
                qualityLabel = session.measuredQualityLabel,
            )
        }
    }

    private fun applyAdaptiveAudioTier(session: PeerSession, tier: Int) {
        if (session.audioQualityTier == tier) return
        session.audioQualityTier = tier
        val values = when (tier) {
            AUDIO_TIER_POOR -> intArrayOf(16_000, 24_000, 36_000)
            AUDIO_TIER_GOOD -> intArrayOf(20_000, 32_000, 48_000)
            else -> intArrayOf(24_000, 40_000, 64_000)
        }
        // FEC remains enabled in SDP at every tier.  Only bitrate bounds adapt here,
        // which avoids destabilizing a field-proven media session mid-ride.
        runCatching { session.pc.setBitrate(values[0], values[1], values[2]) }
    }

    private fun registerRecoveryCallbacks(ctx: Context) {
        val handler = Handler(Looper.getMainLooper())
        recoveryHandler = handler

        val manager = audioManager
        if (manager != null && audioDeviceCallback == null) {
            val callback = object : AudioDeviceCallback() {
                override fun onAudioDevicesAdded(addedDevices: Array<AudioDeviceInfo>) {
                    if (addedDevices.any { it.isVoiceBluetoothDevice() }) scheduleAudioRouteRecovery()
                }

                override fun onAudioDevicesRemoved(removedDevices: Array<AudioDeviceInfo>) {
                    if (removedDevices.any { it.isVoiceBluetoothDevice() }) scheduleAudioRouteRecovery()
                }
            }
            audioDeviceCallback = callback
            runCatching { manager.registerAudioDeviceCallback(callback, handler) }
        }

        val cm = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        connectivityManager = cm
        val active = cm.activeNetwork
        lastNetworkHandle = active?.networkHandle ?: -1L
        lastNetworkTransport = networkTransportLabel(active?.let(cm::getNetworkCapabilities))

        if (networkCallback == null) {
            val callback = object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) {
                    observeDefaultNetwork(network)
                }

                override fun onCapabilitiesChanged(network: Network, capabilities: NetworkCapabilities) {
                    observeDefaultNetwork(network, capabilities)
                }
            }
            networkCallback = callback
            runCatching { cm.registerDefaultNetworkCallback(callback, handler) }
        }
    }

    private fun unregisterRecoveryCallbacks() {
        audioDeviceCallback?.let { callback ->
            runCatching { audioManager?.unregisterAudioDeviceCallback(callback) }
        }
        audioDeviceCallback = null
        networkCallback?.let { callback ->
            runCatching { connectivityManager?.unregisterNetworkCallback(callback) }
        }
        networkCallback = null
        connectivityManager = null
        recoveryHandler?.removeCallbacksAndMessages(null)
        recoveryHandler = null
        networkHandoverPending = false
        lastNetworkHandle = -1L
        lastNetworkTransport = ""
    }

    private fun scheduleAudioRouteRecovery() {
        val handler = recoveryHandler ?: return
        handler.removeCallbacksAndMessages(AUDIO_ROUTE_RECOVERY_TOKEN)
        handler.postAtTime({
            if (!running.get() || focusPaused) return@postAtTime
            selectAudioRoute()
            sessions.values.forEach { session ->
                runCatching { session.pc.setAudioPlayout(true) }
                runCatching { session.pc.setAudioRecording(true) }
            }
            applyVoiceEnabled()
        }, AUDIO_ROUTE_RECOVERY_TOKEN, android.os.SystemClock.uptimeMillis() + AUDIO_ROUTE_RECOVERY_MS)
    }

    private fun observeDefaultNetwork(
        network: Network,
        capabilities: NetworkCapabilities? = connectivityManager?.getNetworkCapabilities(network),
    ) {
        if (!running.get()) return
        val handle = network.networkHandle
        val transport = networkTransportLabel(capabilities)
        val changed = lastNetworkHandle >= 0L &&
            (handle != lastNetworkHandle || (lastNetworkTransport.isNotBlank() && transport != lastNetworkTransport))
        lastNetworkHandle = handle
        lastNetworkTransport = transport
        if (!changed) return

        networkHandoverPending = true
        reconnectAttempt = 0
        listener.onInternetState(voicePeerCount() > 0, "CONNECTION CHANGED • RECOVERING")
        // Force signaling onto the new default network.  Existing media can remain
        // alive until ICE recovery is negotiated after signaling reconnects.
        closeSocket()
    }

    private fun networkTransportLabel(capabilities: NetworkCapabilities?): String = when {
        capabilities == null -> "UNKNOWN"
        capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "WIFI"
        capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "CELLULAR"
        capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ETHERNET"
        else -> "OTHER"
    }

    private fun recoverPeersAfterNetworkHandover() {
        sessions.values.forEach { session ->
            if (session.initiator) {
                runCatching { session.pc.restartIce() }
                session.connected = false
                session.measuredQualityBars = 1
                session.measuredQualityLabel = "Reconnecting"
                maybeCreateOffer(session, force = true)
            } else if (!session.connected) {
                updatePeerState(session.id, "RECONNECTING")
            }
        }
        notifyPeerCount(force = true)
    }

'''
    if insert_anchor not in s:
        raise SystemExit('connectionLoop insertion anchor not found')
    s = s.replace(insert_anchor, helpers + insert_anchor, 1)

# Constants beside existing vc17 reconnect / polling constants.
const_anchor = '        private const val RECONNECT_JITTER_MS = 500L\n'
if 'CONNECTION_HEALTH_POLL_MS' not in s:
    if const_anchor not in s:
        raise SystemExit('reconnect constants anchor not found')
    s = s.replace(
        const_anchor,
        const_anchor
        + '\n        private const val CONNECTION_HEALTH_POLL_MS = 4_000L\n'
        + '        private const val AUDIO_ROUTE_RECOVERY_MS = 550L\n'
        + '        private val AUDIO_ROUTE_RECOVERY_TOKEN = Any()\n'
        + '\n        private const val QUALITY_EXCELLENT_LOSS_PERCENT = 2.0\n'
        + '        private const val QUALITY_EXCELLENT_RTT_MS = 180.0\n'
        + '        private const val QUALITY_EXCELLENT_JITTER_MS = 25.0\n'
        + '        private const val QUALITY_POOR_LOSS_PERCENT = 7.0\n'
        + '        private const val QUALITY_POOR_RTT_MS = 450.0\n'
        + '        private const val QUALITY_POOR_JITTER_MS = 60.0\n'
        + '\n        private const val AUDIO_TIER_POOR = 1\n'
        + '        private const val AUDIO_TIER_GOOD = 2\n'
        + '        private const val AUDIO_TIER_EXCELLENT = 3\n',
        1,
    )

internet.write_text(s)

# Rider UI: use the measured public label directly instead of inferred state bars.
main = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
m = main.read_text()
old_quality_ui = '''                    val quality = when (peer.qualityBars.coerceIn(1, 4)) {
                        4 -> "Excellent"
                        3 -> "Good"
                        2 -> "Fair"
                        else -> "Weak"
                    }
'''
new_quality_ui = '''                    val quality = peer.qualityLabel.ifBlank { "Good" }
'''
if 'peer.qualityLabel.ifBlank' not in m:
    if old_quality_ui not in m:
        raise SystemExit('themed rider quality UI anchor not found')
    m = m.replace(old_quality_ui, new_quality_ui, 1)
main.write_text(m)

# Version vc18; vc17 remains the known-good Play rollback.
gradle = ROOT / 'app/build.gradle.kts'
g = gradle.read_text()
if 'versionCode = 18' not in g:
    if 'versionCode = 17' not in g:
        raise SystemExit('Expected vc17 before Beta5.0 patch')
    g = g.replace('versionCode = 17', 'versionCode = 18', 1)
if 'versionName = "1.0.0-beta5.0-adaptive-reliability"' not in g:
    g, count = re.subn(
        r'versionName = "1\.0\.0-beta4\.9-battery-optimized"',
        'versionName = "1.0.0-beta5.0-adaptive-reliability"',
        g,
        count=1,
    )
    if count != 1:
        raise SystemExit('Expected Beta4.9 versionName before Beta5.0 patch')
gradle.write_text(g)

print('Beta5.0 adaptive reliability applied: quality metrics + adaptive bitrate + route/handover recovery, vc18')
