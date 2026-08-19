from pathlib import Path

root = Path('.')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    if replacement in text:
        return text
    i = text.find(start)
    if i < 0:
        raise SystemExit(f'{label} start anchor not found')
    j = text.find(end, i)
    if j < 0:
        raise SystemExit(f'{label} end anchor not found')
    return text[:i] + replacement + text[j:]


# -----------------------------------------------------------------------------
# Build identity: APK-only Beta3.1 field test.
# -----------------------------------------------------------------------------
p = root / 'app/build.gradle.kts'
s = p.read_text()
s = replace_once(
    s,
    'versionCode = 3\n        versionName = "1.0.0-beta3-audio"',
    'versionCode = 4\n        versionName = "1.0.0-beta3.1-mesh"',
    'build version',
)
p.write_text(s)


# -----------------------------------------------------------------------------
# MeshNode: explicit offline-friendly connection profile + relay diagnostics.
# -----------------------------------------------------------------------------
p = root / 'app/src/main/java/com/bikemesh/ridemesh/mesh/MeshNode.kt'
s = p.read_text()

s = replace_once(
    s,
    'class MeshNode(\n    context: Context,\n    private val listener: Listener,\n) {\n    enum class LabRole { NORMAL, A, B, C }\n',
    '''class MeshNode(\n    context: Context,\n    private val listener: Listener,\n) {\n    enum class LabRole { NORMAL, A, B, C }\n\n    data class Diagnostics(\n        val directPeers: Int,\n        val receivedPackets: Int,\n        val relayedPackets: Int,\n        val maxObservedHops: Int,\n        val profile: String,\n    )\n''',
    'mesh diagnostics data class',
)

s = replace_once(
    s,
    '    private val sequence = AtomicInteger(0)\n',
    '''    private val sequence = AtomicInteger(0)\n    private val receivedPackets = AtomicInteger(0)\n    private val relayedPackets = AtomicInteger(0)\n    private val maxObservedHops = AtomicInteger(0)\n''',
    'mesh counters',
)

s = replace_once(
    s,
    '    private var labRole: LabRole = LabRole.NORMAL\n    @Volatile private var running = false\n',
    '''    private var labRole: LabRole = LabRole.NORMAL\n    private var offlinePreferred = false\n    @Volatile private var running = false\n''',
    'mesh mode field',
)

s = replace_once(
    s,
    '                val packet = MeshPacket.decode(raw) ?: return\n\n                synchronized(seenPackets) {',
    '''                val packet = MeshPacket.decode(raw) ?: return\n                receivedPackets.incrementAndGet()\n                val observedHops = (MAX_TTL - packet.ttl + 1).coerceIn(1, MAX_TTL + 1)\n                maxObservedHops.updateAndGet { previous -> maxOf(previous, observedHops) }\n\n                synchronized(seenPackets) {''',
    'mesh receive diagnostics',
)

s = replace_once(
    s,
    '                if (packet.ttl > 0) {\n                    relay(packet.nextHop(), excludeEndpoint = endpointId)\n                }',
    '''                if (packet.ttl > 0) {\n                    relayedPackets.incrementAndGet()\n                    relay(packet.nextHop(), excludeEndpoint = endpointId)\n                }''',
    'mesh relay counter',
)

s = replace_once(
    s,
    '''                    ConnectionOptions.Builder()\n                        .setConnectionType(ConnectionType.NON_DISRUPTIVE)\n                        .build(),''',
    '''                    ConnectionOptions.Builder()\n                        .setConnectionType(connectionType())\n                        .build(),''',
    'request connection profile',
)

s = replace_once(
    s,
    '''    fun start(\n        riderName: String,\n        rideCode: String,\n        labRole: LabRole = LabRole.NORMAL,\n        deviceName: String = "",\n    ) {''',
    '''    fun start(\n        riderName: String,\n        rideCode: String,\n        labRole: LabRole = LabRole.NORMAL,\n        deviceName: String = "",\n        preferOffline: Boolean = false,\n    ) {''',
    'mesh start signature',
)

s = replace_once(
    s,
    '''        this.rideCode = rideCode.trim().uppercase().ifBlank { "RIDE01" }.take(12)\n        this.labRole = labRole\n        running = true\n        listener.onLog("Starting local mesh for ride ${this.rideCode}")\n\n        val advertising = AdvertisingOptions.Builder()\n            .setStrategy(STRATEGY)\n            .setConnectionType(ConnectionType.NON_DISRUPTIVE)\n            .build()''',
    '''        this.rideCode = rideCode.trim().uppercase().ifBlank { "RIDE01" }.take(12)\n        this.labRole = labRole\n        this.offlinePreferred = preferOffline\n        receivedPackets.set(0)\n        relayedPackets.set(0)\n        maxObservedHops.set(0)\n        running = true\n        listener.onLog("Starting local mesh for ride ${this.rideCode} • ${if (preferOffline) "OFFLINE BALANCED" else "HYBRID"}")\n\n        val advertising = AdvertisingOptions.Builder()\n            .setStrategy(STRATEGY)\n            .setConnectionType(connectionType())\n            .build()''',
    'mesh offline profile setup',
)

insert_anchor = '    fun endpointIdForSource(sourceId: String): String? = runCatching {\n'
insert_text = '''    fun diagnostics(): Diagnostics = Diagnostics(\n        directPeers = connected.size,\n        receivedPackets = receivedPackets.get(),\n        relayedPackets = relayedPackets.get(),\n        maxObservedHops = maxObservedHops.get(),\n        profile = if (offlinePreferred) "OFFLINE BALANCED" else "HYBRID NON-DISRUPTIVE",\n    )\n\n    private fun connectionType(): Int = if (offlinePreferred) {\n        ConnectionType.BALANCED\n    } else {\n        ConnectionType.NON_DISRUPTIVE\n    }\n\n'''
if insert_text not in s:
    if insert_anchor not in s:
        raise SystemExit('mesh diagnostics insertion anchor not found')
    s = s.replace(insert_anchor, insert_text + insert_anchor, 1)

p.write_text(s)


# -----------------------------------------------------------------------------
# AudioEngine: fully yield microphone/output/communication route to phone/VoIP
# calls and other apps that take audio focus, then recover hands-free afterward.
# -----------------------------------------------------------------------------
p = root / 'app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt'
s = p.read_text()

pause_start = '    private fun pauseForAudioFocus() {'
pause_end = '    private fun clearRemoteAudio() {'
new_pause = '''    private fun pauseForAudioFocus() {\n        if (!focusPaused.compareAndSet(false, true)) return\n        capturing.set(false)\n        // Stop the recorder immediately so RideMesh cannot leak a phone/WhatsApp call\n        // into the ride while another communication app owns audio focus.\n        try { audioRecord?.stop() } catch (_: Throwable) {}\n        clearRemoteAudio()\n        audioTrack?.let {\n            try { it.pause() } catch (_: Throwable) {}\n            try { it.flush() } catch (_: Throwable) {}\n        }\n        releaseCommunicationRouteForExternalCall()\n        onStatus("CALL / OTHER AUDIO ACTIVE • RIDEMESH PAUSED")\n    }\n\n    private fun resumeAfterAudioFocus() {\n        focusHeld.set(true)\n        if (!focusPaused.compareAndSet(true, false)) return\n        Thread({\n            try { Thread.sleep(CALL_RESUME_SETTLE_MS) } catch (_: InterruptedException) { return@Thread }\n            if (focusPaused.get()) return@Thread\n            selectCommunicationDevice()\n            audioTrack?.let {\n                try { it.play() } catch (_: Throwable) {}\n            }\n            onStatus("HANDS-FREE • AUDIO RESUMED")\n            if (transmitDesired.get()) startRecorder()\n        }, "RideMesh-CallResume").apply { isDaemon = true; start() }\n    }\n\n    @Suppress("DEPRECATION")\n    private fun releaseCommunicationRouteForExternalCall() {\n        try {\n            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {\n                audioManager.clearCommunicationDevice()\n            } else {\n                runCatching { audioManager.stopBluetoothSco() }\n                audioManager.isBluetoothScoOn = false\n                audioManager.isSpeakerphoneOn = false\n            }\n            audioManager.mode = AudioManager.MODE_NORMAL\n        } catch (_: Throwable) {\n            // The external call already has priority; failing to clear one route must not\n            // cause RideMesh to fight for audio.\n        }\n    }\n\n'''
s = replace_between(s, pause_start, pause_end, new_pause, 'audio focus pause/resume')

s = replace_once(
    s,
    '                } catch (t: Throwable) {\n                    onStatus("Microphone stream error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")\n                } finally {',
    '''                } catch (t: Throwable) {\n                    if (!focusPaused.get()) {\n                        onStatus("Microphone stream error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")\n                    }\n                } finally {''',
    'suppress expected call interruption error',
)

s = replace_once(
    s,
    '''    fun stopTransmit() {\n        transmitDesired.set(false)\n        capturing.set(false)\n    }''',
    '''    fun stopTransmit() {\n        transmitDesired.set(false)\n        capturing.set(false)\n        try { audioRecord?.stop() } catch (_: Throwable) {}\n        clearRemoteAudio()\n        releaseCommunicationRouteForExternalCall()\n        if (focusHeld.getAndSet(false)) {\n            runCatching { audioManager.abandonAudioFocusRequest(audioFocusRequest) }\n        }\n    }''',
    'stop transmit focus cleanup',
)

const_anchor = '        private const val PLAYBACK_IDLE_SLEEP_MS = 3L\n'
s = replace_once(
    s,
    const_anchor,
    const_anchor + '        private const val CALL_RESUME_SETTLE_MS = 350L\n',
    'call resume settle constant',
)
p.write_text(s)


# -----------------------------------------------------------------------------
# MainActivity: explicit AUTO / LOCAL ONLY / INTERNET ONLY modes, A/B/C relay
# lab roles, and diagnostics. Local-only never starts MQTT and never sleeps mesh.
# -----------------------------------------------------------------------------
p = root / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

s = replace_once(
    s,
    '''    private var micMuted = false\n    private var betaExpiredDialogShown = false\n\n    private enum class PendingAction { NONE, START_RIDE, FIND_RIDERS }''',
    '''    private var micMuted = false\n    private var betaExpiredDialogShown = false\n    private var transportMode = TransportMode.AUTO\n    private var meshLabRole = MeshNode.LabRole.NORMAL\n\n    private enum class TransportMode { AUTO, LOCAL_ONLY, INTERNET_ONLY }\n    private enum class PendingAction { NONE, START_RIDE, FIND_RIDERS }''',
    'transport fields',
)

watch_start = '    private val rideWatchdog = object : Runnable {'
watch_end = '    private val permissionLauncher = registerForActivityResult('
new_watch = '''    private val rideWatchdog = object : Runnable {\n        override fun run() {\n            if (!rideStarted) return\n            if (isBetaExpired()) {\n                expireActiveRide()\n                return\n            }\n\n            val now = System.currentTimeMillis()\n            when (transportMode) {\n                TransportMode.LOCAL_ONLY -> {\n                    ensureLocalMeshRunning("LOCAL MESH ONLY")\n                    if (meshRunning && directPeerCount == 0 && now - lastMeshRefreshMs >= LOCAL_MESH_REFRESH_MS) {\n                        restartLocalMesh()\n                    }\n                }\n\n                TransportMode.INTERNET_ONLY -> {\n                    if (meshRunning) sleepLocalMesh("INTERNET ONLY")\n                }\n\n                TransportMode.AUTO -> {\n                    if (internetNode.isConnected()) {\n                        val stableFor = now - internetConnectedSinceMs\n                        if (binding.batterySaver.isChecked && stableFor >= INTERNET_STABLE_BEFORE_MESH_SLEEP_MS) {\n                            sleepLocalMesh("Internet stable")\n                        } else {\n                            ensureLocalMeshRunning("warm handover fallback")\n                        }\n                    } else {\n                        ensureLocalMeshRunning("Internet unavailable")\n                        if (meshRunning && directPeerCount == 0 && now - lastMeshRefreshMs >= LOCAL_MESH_REFRESH_MS) {\n                            restartLocalMesh()\n                        }\n                    }\n                }\n            }\n\n            updateTransportStatus()\n            updateCapturePolicy()\n            mainHandler.postDelayed(this, WATCHDOG_INTERVAL_MS)\n        }\n    }\n\n'''
s = replace_between(s, watch_start, watch_end, new_watch, 'ride watchdog')

start_start = '    private fun startRideNow() {'
start_end = '    private fun sendHybridAudio(audio: ByteArray) {'
new_start = '''    private fun startRideNow() {\n        if (rideStarted || !ensureBetaUsable()) return\n\n        setMicMuted(false)\n        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }\n        val code = normalizedRideCode()\n        binding.riderName.setText(rider)\n        binding.rideCode.setText(code)\n        saveSettings()\n\n        try {\n            stopLobbyDiscovery()\n            startRideServiceSafely()\n\n            rideStarted = true\n            directPeerCount = 0\n            internetPeerCount = 0\n            meshRunning = false\n            internetConnectedSinceMs = 0L\n            lastMeshRefreshMs = 0L\n\n            applySelectedAudioRoute()\n            audioEngine.selectCommunicationDevice()\n\n            when (transportMode) {\n                TransportMode.AUTO -> {\n                    ensureLocalMeshRunning("initial fallback")\n                    internetNode.start(code, rider, deviceLabel())\n                }\n                TransportMode.LOCAL_ONLY -> {\n                    ensureLocalMeshRunning("offline test mode")\n                    log("LOCAL MESH ONLY • Internet voice disabled • A/B/C relay test ready")\n                }\n                TransportMode.INTERNET_ONLY -> {\n                    internetNode.start(code, rider, deviceLabel())\n                    log("INTERNET ONLY • local mesh disabled for diagnostics")\n                }\n            }\n\n            binding.activeRideCode.text = code\n            showScreen(Screen.ACTIVE)\n            updateTransportStatus()\n            updateCapturePolicy()\n\n            mainHandler.removeCallbacks(rideWatchdog)\n            mainHandler.postDelayed(rideWatchdog, WATCHDOG_INTERVAL_MS)\n            log("Ride started • ${transportModeLabel()} • call-safe audio focus enabled")\n        } catch (t: Throwable) {\n            recoverFromStartFailure(t)\n        }\n    }\n\n'''
s = replace_between(s, start_start, start_end, new_start, 'start ride mode')

send_start = '    private fun sendHybridAudio(audio: ByteArray) {'
send_end = '    private fun ensureLocalMeshRunning(reason: String) {'
new_send = '''    private fun sendHybridAudio(audio: ByteArray) {\n        if (!rideStarted || audio.isEmpty()) return\n\n        when (transportMode) {\n            TransportMode.LOCAL_ONLY -> {\n                ensureLocalMeshRunning("local voice path")\n                meshNode.sendLocalAudio(audio)\n            }\n            TransportMode.INTERNET_ONLY -> {\n                if (internetNode.isConnected()) internetNode.sendLocalAudio(audio)\n            }\n            TransportMode.AUTO -> {\n                if (internetNode.isConnected()) {\n                    if (!internetNode.sendLocalAudio(audio)) {\n                        ensureLocalMeshRunning("Internet send failed")\n                        meshNode.sendLocalAudio(audio)\n                    }\n                } else {\n                    ensureLocalMeshRunning("local voice path")\n                    meshNode.sendLocalAudio(audio)\n                }\n            }\n        }\n    }\n\n'''
s = replace_between(s, send_start, send_end, new_send, 'hybrid router')

mesh_start = '    private fun ensureLocalMeshRunning(reason: String) {'
mesh_end = '    private fun sleepLocalMesh(reason: String) {'
new_mesh = '''    private fun ensureLocalMeshRunning(reason: String) {\n        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || meshRunning || !radiosReady()) return\n        meshNode.start(\n            binding.riderName.text?.toString().orEmpty(),\n            normalizedRideCode(),\n            meshLabRole,\n            deviceLabel(),\n            preferOffline = transportMode == TransportMode.LOCAL_ONLY,\n        )\n        meshRunning = true\n        lastMeshRefreshMs = System.currentTimeMillis()\n        log("Local mesh awake • $reason • role ${meshLabRole.name}")\n    }\n\n'''
s = replace_between(s, mesh_start, mesh_end, new_mesh, 'ensure local mesh')

restart_start = '    private fun restartLocalMesh() {'
restart_end = '    private fun applyBatteryPolicy() {'
new_restart = '''    private fun restartLocalMesh() {\n        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || !radiosReady()) return\n        if (transportMode == TransportMode.AUTO && internetNode.isConnected()) return\n        log("Refreshing local discovery for automatic reconnect")\n        meshRunning = false\n        meshNode.stop()\n        directPeerCount = 0\n        ensureLocalMeshRunning("automatic reconnect refresh")\n    }\n\n    private fun restartLocalMeshForRoleOrMode(reason: String) {\n        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY) return\n        if (meshRunning) {\n            meshRunning = false\n            meshNode.stop()\n            directPeerCount = 0\n        }\n        ensureLocalMeshRunning(reason)\n    }\n\n'''
s = replace_between(s, restart_start, restart_end, new_restart, 'restart local mesh')

battery_start = '    private fun applyBatteryPolicy() {'
battery_end = '    private fun updateCapturePolicy() {'
new_battery = '''    private fun applyBatteryPolicy() {\n        applyPowerUi()\n        if (!rideStarted) return\n\n        when (transportMode) {\n            TransportMode.LOCAL_ONLY -> ensureLocalMeshRunning("LOCAL ONLY ignores mesh sleep")\n            TransportMode.INTERNET_ONLY -> if (meshRunning) sleepLocalMesh("INTERNET ONLY")\n            TransportMode.AUTO -> {\n                if (!binding.batterySaver.isChecked) {\n                    ensureLocalMeshRunning("Max Link selected")\n                } else if (!internetNode.isConnected()) {\n                    ensureLocalMeshRunning("Internet unavailable")\n                }\n            }\n        }\n\n        updateTransportStatus()\n        updateCapturePolicy()\n    }\n\n'''
s = replace_between(s, battery_start, battery_end, new_battery, 'battery policy')

capture_start = '    private fun updateCapturePolicy() {'
capture_end = '    private fun startRideServiceSafely() {'
new_capture = '''    private fun updateCapturePolicy() {\n        if (!rideStarted) return\n        val voicePathReady = when (transportMode) {\n            TransportMode.LOCAL_ONLY -> directPeerCount > 0\n            TransportMode.INTERNET_ONLY -> internetNode.isConnected()\n            TransportMode.AUTO -> internetNode.isConnected() || directPeerCount > 0\n        }\n        if (voicePathReady) {\n            audioEngine.startTransmit()\n        } else {\n            audioEngine.stopTransmit()\n            updateAudioUi("Reconnecting • microphone sleeping")\n        }\n    }\n\n'''
s = replace_between(s, capture_start, capture_end, new_capture, 'capture policy')

s = replace_once(
    s,
    '        binding.batterySaver.isChecked = prefs.getBoolean("battery_smart", true)\n\n        when (prefs.getString("audio_route", "AUTO")) {',
    '''        binding.batterySaver.isChecked = prefs.getBoolean("battery_smart", true)\n        transportMode = runCatching {\n            TransportMode.valueOf(prefs.getString("transport_mode", TransportMode.AUTO.name).orEmpty())\n        }.getOrDefault(TransportMode.AUTO)\n        meshLabRole = runCatching {\n            MeshNode.LabRole.valueOf(prefs.getString("mesh_lab_role", MeshNode.LabRole.NORMAL.name).orEmpty())\n        }.getOrDefault(MeshNode.LabRole.NORMAL)\n\n        when (prefs.getString("audio_route", "AUTO")) {''',
    'restore transport settings',
)

s = replace_once(
    s,
    '            .putBoolean("battery_smart", binding.batterySaver.isChecked)\n            .apply()',
    '''            .putBoolean("battery_smart", binding.batterySaver.isChecked)\n            .putString("transport_mode", transportMode.name)\n            .putString("mesh_lab_role", meshLabRole.name)\n            .apply()''',
    'save transport settings',
)

internet_state_start = '    override fun onInternetState(connected: Boolean, message: String) {'
internet_state_end = '    override fun onInternetPeerCount(count: Int) {'
new_internet_state = '''    override fun onInternetState(connected: Boolean, message: String) {\n        runOnUiThread {\n            log(message)\n            if (connected) {\n                if (internetConnectedSinceMs == 0L) internetConnectedSinceMs = System.currentTimeMillis()\n            } else {\n                internetConnectedSinceMs = 0L\n                stopLobbyDiscovery()\n                if (rideStarted && transportMode == TransportMode.AUTO) {\n                    ensureLocalMeshRunning("Internet path lost")\n                }\n            }\n            updateTransportStatus()\n            updateCapturePolicy()\n        }\n    }\n\n'''
s = replace_between(s, internet_state_start, internet_state_end, new_internet_state, 'internet state')

status_start = '    private fun updateTransportStatus() {'
status_end = '    private fun markRiderSpeaking(key: String) {'
new_status = '''    private fun updateTransportStatus() {\n        if (!rideStarted) return\n\n        when (transportMode) {\n            TransportMode.LOCAL_ONLY -> {\n                binding.networkTile.text = if (directPeerCount > 0) "LOCAL MESH" else "MESH SEARCH"\n                binding.riderCount.text = "RIDE ACTIVE"\n                binding.meshStatus.text = if (directPeerCount > 0) {\n                    "OFFLINE LOCAL VOICE • ROLE ${meshLabRole.name}"\n                } else {\n                    "OFFLINE SEARCH • WIFI + BLUETOOTH • ROLE ${meshLabRole.name}"\n                }\n            }\n            TransportMode.INTERNET_ONLY -> {\n                binding.networkTile.text = if (internetNode.isConnected()) "INTERNET" else "NET SEARCH"\n                binding.riderCount.text = "RIDE ACTIVE"\n                binding.meshStatus.text = "INTERNET ONLY • LOCAL MESH DISABLED"\n            }\n            TransportMode.AUTO -> {\n                when {\n                    internetNode.isConnected() -> {\n                        binding.networkTile.text = "INTERNET"\n                        binding.riderCount.text = "RIDE ACTIVE"\n                        binding.meshStatus.text = if (binding.batterySaver.isChecked && !meshRunning) {\n                            "INTERNET VOICE • AUTO LOCAL FALLBACK"\n                        } else {\n                            "INTERNET VOICE • LOCAL MESH WARM"\n                        }\n                    }\n                    directPeerCount > 0 -> {\n                        binding.networkTile.text = "LOCAL MESH"\n                        binding.riderCount.text = "RIDE ACTIVE"\n                        binding.meshStatus.text = "LOCAL VOICE • AUTO RECONNECT ACTIVE"\n                    }\n                    else -> {\n                        binding.networkTile.text = "SEARCHING"\n                        binding.riderCount.text = "RIDE ACTIVE"\n                        binding.meshStatus.text = "AUTO RECONNECT • INTERNET + NEARBY SEARCH"\n                    }\n                }\n            }\n        }\n\n        binding.homeNetworkStatus.text = when (transportMode) {\n            TransportMode.LOCAL_ONLY -> "Offline Mesh\\n${if (directPeerCount > 0) "Active" else "Ready"}"\n            TransportMode.INTERNET_ONLY -> "Internet Only\\n${if (internetNode.isConnected()) "Active" else "Ready"}"\n            TransportMode.AUTO -> when {\n                internetNode.isConnected() -> "Internet Voice\\nActive"\n                directPeerCount > 0 -> "Local Mesh\\nActive"\n                else -> "Internet + Mesh\\nReady"\n            }\n        }\n\n        val visibleRiderTotal = when (transportMode) {\n            TransportMode.LOCAL_ONLY -> if (directPeerCount > 0) directPeerCount + 1 else 1\n            TransportMode.INTERNET_ONLY -> if (internetNode.isConnected()) internetPeerCount + 1 else 1\n            TransportMode.AUTO -> when {\n                internetNode.isConnected() -> internetPeerCount + 1\n                directPeerCount > 0 -> directPeerCount + 1\n                else -> 1\n            }\n        }\n        binding.activeRiders.text = "RIDERS $visibleRiderTotal"\n        renderRiderGrid()\n        applyPowerUi()\n    }\n\n'''
s = replace_between(s, status_start, status_end, new_status, 'transport status')

settings_start = '    private fun showSettingsAndHelpDialog() {'
settings_end = '    private fun ensureBetaFirstLaunch(): Long {'
new_settings = '''    private fun transportModeLabel(): String = when (transportMode) {\n        TransportMode.AUTO -> "AUTO HYBRID"\n        TransportMode.LOCAL_ONLY -> "LOCAL MESH ONLY"\n        TransportMode.INTERNET_ONLY -> "INTERNET ONLY"\n    }\n\n    private fun showTransportModeDialog() {\n        val choices = arrayOf(\n            "AUTO HYBRID — Internet first + local fallback",\n            "LOCAL MESH ONLY — offline / multi-hop test",\n            "INTERNET ONLY — isolate Internet audio",\n        )\n        val checked = when (transportMode) {\n            TransportMode.AUTO -> 0\n            TransportMode.LOCAL_ONLY -> 1\n            TransportMode.INTERNET_ONLY -> 2\n        }\n        AlertDialog.Builder(this)\n            .setTitle("Transport test mode")\n            .setSingleChoiceItems(choices, checked) { dialog, which ->\n                transportMode = when (which) {\n                    1 -> TransportMode.LOCAL_ONLY\n                    2 -> TransportMode.INTERNET_ONLY\n                    else -> TransportMode.AUTO\n                }\n                saveSettings()\n                if (rideStarted) applyTransportModeChange()\n                dialog.dismiss()\n            }\n            .setNeutralButton("A / B / C ROLE") { _, _ -> showMeshLabRoleDialog() }\n            .setNegativeButton("CANCEL", null)\n            .show()\n    }\n\n    private fun showMeshLabRoleDialog() {\n        val choices = arrayOf(\n            "NORMAL — normal riding group",\n            "A — connects only to B",\n            "B — relay between A and C",\n            "C — connects only to B",\n        )\n        val checked = when (meshLabRole) {\n            MeshNode.LabRole.NORMAL -> 0\n            MeshNode.LabRole.A -> 1\n            MeshNode.LabRole.B -> 2\n            MeshNode.LabRole.C -> 3\n        }\n        AlertDialog.Builder(this)\n            .setTitle("Offline multi-hop lab role")\n            .setSingleChoiceItems(choices, checked) { dialog, which ->\n                meshLabRole = when (which) {\n                    1 -> MeshNode.LabRole.A\n                    2 -> MeshNode.LabRole.B\n                    3 -> MeshNode.LabRole.C\n                    else -> MeshNode.LabRole.NORMAL\n                }\n                saveSettings()\n                if (rideStarted && transportMode != TransportMode.INTERNET_ONLY) {\n                    restartLocalMeshForRoleOrMode("lab role changed to ${meshLabRole.name}")\n                    updateTransportStatus()\n                    updateCapturePolicy()\n                }\n                dialog.dismiss()\n            }\n            .setNegativeButton("CANCEL", null)\n            .show()\n    }\n\n    private fun applyTransportModeChange() {\n        if (!rideStarted) return\n        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }\n        val code = normalizedRideCode()\n        audioEngine.stopTransmit()\n\n        when (transportMode) {\n            TransportMode.LOCAL_ONLY -> {\n                internetNode.stop()\n                internetPeerCount = 0\n                internetConnectedSinceMs = 0L\n                restartLocalMeshForRoleOrMode("switched to LOCAL MESH ONLY")\n            }\n            TransportMode.INTERNET_ONLY -> {\n                if (meshRunning) sleepLocalMesh("switched to INTERNET ONLY")\n                internetNode.stop()\n                internetPeerCount = 0\n                internetNode.start(code, rider, deviceLabel())\n            }\n            TransportMode.AUTO -> {\n                restartLocalMeshForRoleOrMode("switched to AUTO HYBRID")\n                internetNode.stop()\n                internetPeerCount = 0\n                internetNode.start(code, rider, deviceLabel())\n            }\n        }\n        log("Transport mode: ${transportModeLabel()} • role ${meshLabRole.name}")\n        updateTransportStatus()\n        updateCapturePolicy()\n    }\n\n    private fun showSettingsAndHelpDialog() {\n        val modes = arrayOf(\n            "Battery Smart — recommended",\n            "Max Link — keep Internet + local mesh active",\n        )\n        val checked = if (binding.batterySaver.isChecked) 0 else 1\n\n        AlertDialog.Builder(this)\n            .setTitle("RideMesh settings & help")\n            .setSingleChoiceItems(modes, checked) { dialog, which ->\n                binding.batterySaver.isChecked = which == 0\n                saveSettings()\n                applyBatteryPolicy()\n                dialog.dismiss()\n            }\n            .setMessage(\n                "Transport: ${transportModeLabel()} • Mesh role ${meshLabRole.name}\\n\\n" +\n                    "RideMesh automatically pauses microphone and playback when a phone/WhatsApp/VoIP call takes Android audio focus, then resumes after the call.\\n\\n" +\n                    "LOCAL MESH ONLY keeps Internet voice off and prevents mesh sleeping for offline testing. Wi-Fi + Bluetooth should be ON; Internet may be OFF.\\n\\n" +\n                    betaStatusSentence() + "\\n\\n" +\n                    "Bug reports: WhatsApp group or direct support +91 9188664823."\n            )\n            .setPositiveButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }\n            .setNeutralButton("TRANSPORT") { _, _ -> showTransportModeDialog() }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n'''
s = replace_between(s, settings_start, settings_end, new_settings, 'settings and transport dialogs')

ride_status_start = '    private fun showRideStatusDialog() {'
ride_status_end = '    private fun openWhatsAppBugReport() {'
new_ride_status = '''    private fun showRideStatusDialog() {\n        val path = when (transportMode) {\n            TransportMode.LOCAL_ONLY -> if (directPeerCount > 0) "Offline local mesh" else "Offline mesh searching"\n            TransportMode.INTERNET_ONLY -> if (internetNode.isConnected()) "Internet only" else "Internet reconnecting"\n            TransportMode.AUTO -> when {\n                internetNode.isConnected() -> "Internet"\n                directPeerCount > 0 -> "Local mesh"\n                else -> "Reconnecting"\n            }\n        }\n        val diag = meshNode.diagnostics()\n\n        AlertDialog.Builder(this)\n            .setTitle("Ride status • ${transportModeLabel()}")\n            .setMessage(\n                "Path: $path\\n" +\n                    "Mesh role: ${meshLabRole.name}\\n" +\n                    "Direct local peers: $directPeerCount\\n" +\n                    "Mesh profile: ${diag.profile}\\n" +\n                    "Mesh packets received: ${diag.receivedPackets}\\n" +\n                    "Packets relayed by this phone: ${diag.relayedPackets}\\n" +\n                    "Max observed hops: ${diag.maxObservedHops}\\n" +\n                    "Internet riders: ${if (internetNode.isConnected()) internetPeerCount + 1 else 0}\\n" +\n                    "Audio: ${binding.audioTile.text}\\n" +\n                    "Microphone: ${if (micMuted) "MUTED" else "LIVE"}\\n" +\n                    "Call-safe audio focus: ON\\n" +\n                    "Power: ${binding.powerTile.text}\\n" +\n                    betaStatusSentence() + "\\n\\n" +\n                    "A→B→C test: set LOCAL MESH ONLY on all three phones, then roles A, B and C. C should hear A only through B."\n            )\n            .setPositiveButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }\n            .setNeutralButton("TRANSPORT") { _, _ -> showTransportModeDialog() }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n'''
s = replace_between(s, ride_status_start, ride_status_end, new_ride_status, 'ride diagnostics')

p.write_text(s)

print('RideMesh Beta3.1 mesh recovery + call-safe patch applied')
