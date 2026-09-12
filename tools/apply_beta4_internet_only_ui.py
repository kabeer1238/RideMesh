from pathlib import Path
import re

ROOT = Path('.')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    return text.replace(old, new, 1)


def sub_once(text: str, pattern: str, replacement: str, label: str) -> str:
    # Use a callable replacement so regex does not reinterpret backslashes such as
    # Kotlin string literals containing \\n.
    out, count = re.subn(pattern, lambda _match: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: pattern count {count}')
    return out


# -----------------------------------------------------------------------------
# MainActivity: Beta4 customer flow is Internet-only WebRTC + Opus.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

s = replace_once(
    s,
    '        internetNode = InternetNode(this)\n',
    '        internetNode = InternetNode(this, applicationContext)\n',
    'InternetNode context',
)

# Hide all customer-facing Nearby discovery controls. QR/code invite remains.
s = replace_once(
    s,
    '''        binding.findNearby.setOnClickListener {\n            ensurePermissionsAndRun(PendingAction.FIND_RIDERS)\n        }\n''',
    '''        binding.findNearby.visibility = View.GONE\n        binding.nearbyUsers.visibility = View.GONE\n''',
    'hide Nearby controls',
)

# Invite menu: QR/code only.
s = sub_once(
    s,
    r'''    private fun showLiveInviteOptions\(\) \{.*?    \}\n\n    private fun buildRideQrBitmap''',
    '''    private fun showLiveInviteOptions() {\n        val options = arrayOf(\n            "Show QR code",\n            "Share QR code",\n        )\n        AlertDialog.Builder(this)\n            .setTitle("Invite riders")\n            .setItems(options) { _, which ->\n                when (which) {\n                    0 -> showRideQr()\n                    1 -> shareRideQr()\n                }\n            }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n    private fun buildRideQrBitmap''',
    'live invite menu',
)

# Start one Internet/WebRTC ride only. No local mesh is started in Beta4.
s = sub_once(
    s,
    r'''    private fun startRideNow\(\) \{.*?    \}\n\n    private fun sendHybridAudio''',
    '''    private fun startRideNow() {\n        if (rideStarted || !ensureBetaUsable()) return\n\n        setMicMuted(false)\n        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }\n        val code = normalizedRideCode()\n        binding.riderName.setText(rider)\n        binding.rideCode.setText(code)\n        transportMode = TransportMode.INTERNET_ONLY\n        meshLabRole = MeshNode.LabRole.NORMAL\n        saveSettings()\n\n        try {\n            stopLobbyDiscovery()\n            startRideServiceSafely()\n\n            rideStarted = true\n            directPeerCount = 0\n            internetPeerCount = 0\n            meshRunning = false\n            internetConnectedSinceMs = 0L\n            lastMeshRefreshMs = 0L\n\n            // Beta4 voice is captured and rendered directly by WebRTC. The old PCM\n            // AudioEngine stays idle so it cannot create a second microphone/audio path.\n            internetNode.start(code, rider, deviceLabel())\n            internetNode.setMuted(micMuted)\n            applySelectedAudioRoute()\n\n            binding.activeRideCode.text = code\n            showScreen(Screen.ACTIVE)\n            updateTransportStatus()\n            updateCapturePolicy()\n\n            mainHandler.removeCallbacks(rideWatchdog)\n            mainHandler.postDelayed(rideWatchdog, WATCHDOG_INTERVAL_MS)\n            log("Ride started • INTERNET WEBRTC + OPUS • call-safe audio focus enabled")\n        } catch (t: Throwable) {\n            recoverFromStartFailure(t)\n        }\n    }\n\n    private fun sendHybridAudio''',
    'start Internet WebRTC ride',
)

# Old callback remains wired to an idle AudioEngine only as a compile-safe fallback.
s = sub_once(
    s,
    r'''    private fun sendHybridAudio\(audio: ByteArray\) \{.*?    \}\n\n    private fun ensureLocalMeshRunning''',
    '''    private fun sendHybridAudio(audio: ByteArray) {\n        // Beta4 does not send PCM frames from this legacy engine. WebRTC owns voice capture.\n    }\n\n    private fun ensureLocalMeshRunning''',
    'disable PCM sender',
)

# Never start the legacy AudioRecord path. WebRTC local AudioTrack controls capture itself.
s = sub_once(
    s,
    r'''    private fun updateCapturePolicy\(\) \{.*?    \}\n\n    private fun startRideServiceSafely''',
    '''    private fun updateCapturePolicy() {\n        if (!rideStarted) return\n        val status = when {\n            micMuted -> "MIC MUTED • LISTENING ONLY"\n            internetNode.voicePeerCount() > 0 -> internetNode.currentAudioStatus()\n            internetNode.isConnected() -> "WEBRTC SIGNALING READY • WAITING FOR RIDERS"\n            else -> "WEBRTC CONNECTING • MIC READY"\n        }\n        updateAudioUi(status)\n    }\n\n    private fun startRideServiceSafely''',
    'WebRTC capture policy',
)

s = replace_once(
    s,
    '            .setMessage("RideMesh stayed open. Check Bluetooth, Wi-Fi and permissions, then try again.")',
    '            .setMessage("RideMesh stayed open. Check Internet access and microphone permission, then try again.")',
    'start failure copy',
)

s = replace_once(
    s,
    '        binding.homeNetworkStatus.text = "Internet + Mesh\\nReady"\n',
    '        binding.homeNetworkStatus.text = "WebRTC Voice\\nReady"\n',
    'stop home network copy',
)

# Audio route is owned by the WebRTC JavaAudioDeviceModule / Android communication device.
s = sub_once(
    s,
    r'''    private fun applySelectedAudioRoute\(\) \{.*?    \}\n\n    private fun updateAudioUi''',
    '''    private fun applySelectedAudioRoute() {\n        if (!::internetNode.isInitialized) return\n        val route = when (binding.audioRoute.checkedRadioButtonId) {\n            R.id.routePhone -> "PHONE"\n            R.id.routeHelmet -> "HELMET"\n            else -> "AUTO"\n        }\n        if (rideStarted) updateAudioUi(internetNode.setAudioRoute(route))\n        else internetNode.setAudioRoute(route)\n    }\n\n    private fun updateAudioUi''',
    'WebRTC audio route',
)

s = replace_once(
    s,
    '''        if (::audioEngine.isInitialized) audioEngine.setUserMuted(muted)\n''',
    '''        if (::internetNode.isInitialized) internetNode.setMuted(muted)\n''',
    'WebRTC mute',
)

# Ignore old saved experimental modes: Beta4 is always Internet-only.
s = sub_once(
    s,
    r'''        transportMode = runCatching \{\n            TransportMode\.valueOf\(prefs\.getString\("transport_mode", TransportMode\.AUTO\.name\)\.orEmpty\(\)\)\n        \}\.getOrDefault\(TransportMode\.AUTO\)\n        meshLabRole = runCatching \{\n            MeshNode\.LabRole\.valueOf\(prefs\.getString\("mesh_lab_role", MeshNode\.LabRole\.NORMAL\.name\)\.orEmpty\(\)\)\n        \}\.getOrDefault\(MeshNode\.LabRole\.NORMAL\)''',
    '''        transportMode = TransportMode.INTERNET_ONLY\n        meshLabRole = MeshNode.LabRole.NORMAL''',
    'force Internet-only settings',
)

# Beta4 runtime permission prompt no longer requests Nearby / Wi-Fi / location permissions.
s = sub_once(
    s,
    r'''    private fun requiredPermissions\(\): List<String> = buildList \{.*?    \}\n\n    override fun onLog''',
    '''    private fun requiredPermissions(): List<String> = buildList {\n        add(Manifest.permission.RECORD_AUDIO)\n        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {\n            add(Manifest.permission.BLUETOOTH_CONNECT)\n        }\n    }\n\n    override fun onLog''',
    'Internet-only runtime permissions',
)

# Mesh callbacks remain only because the archived experimental source compiles in this branch.
s = sub_once(
    s,
    r'''    override fun onInternetState\(connected: Boolean, message: String\) \{.*?    \}\n\n    override fun onInternetPeerCount''',
    '''    override fun onInternetState(connected: Boolean, message: String) {\n        runOnUiThread {\n            log(message)\n            internetConnectedSinceMs = if (connected) System.currentTimeMillis() else 0L\n            updateTransportStatus()\n            updateCapturePolicy()\n        }\n    }\n\n    override fun onInternetPeerCount''',
    'Internet state no local fallback',
)

s = replace_once(
    s,
    '''    override fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {\n        if (!rideStarted) return\n        markRiderSpeaking(sourceId)\n        audioEngine.playIncoming(sourceId, sequence, timestampMs, audio)\n    }''',
    '''    override fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {\n        // Beta4 WebRTC renders remote audio internally. Legacy PCM callback is intentionally unused.\n    }\n\n    override fun onInternetAudioStatus(message: String) {\n        runOnUiThread {\n            if (rideStarted) updateAudioUi(message)\n        }\n    }''',
    'WebRTC remote audio callback',
)

# One simple Internet/WebRTC status model.
s = sub_once(
    s,
    r'''    private fun updateTransportStatus\(\) \{.*?    \}\n\n    private fun markRiderSpeaking''',
    '''    private fun updateTransportStatus() {\n        if (!rideStarted) return\n        val diag = internetNode.diagnostics()\n\n        binding.networkTile.text = when {\n            diag.voicePeersConnected > 0 -> "WEBRTC"\n            diag.signalingConnected -> "INTERNET"\n            else -> "NET SEARCH"\n        }\n        binding.riderCount.text = "RIDE ACTIVE"\n        binding.meshStatus.text = when {\n            diag.voicePeersConnected > 0 ->\n                "OPUS VOICE • ${diag.voicePeersConnected} DIRECT PEER${if (diag.voicePeersConnected == 1) "" else "S"}"\n            diag.signalingConnected -> "SIGNALING READY • WAITING FOR RIDERS"\n            else -> "INTERNET RECONNECTING • WEBRTC AUTO RETRY"\n        }\n        binding.homeNetworkStatus.text = if (internetNode.isConnected()) {\n            "WebRTC Voice\\nActive"\n        } else {\n            "WebRTC Voice\\nReady"\n        }\n\n        val visibleRiderTotal = if (internetNode.isConnected()) internetPeerCount + 1 else 1\n        binding.activeRiders.text = "RIDERS $visibleRiderTotal"\n        renderRiderGrid()\n        applyPowerUi()\n    }\n\n    private fun markRiderSpeaking''',
    'Internet-only status',
)

# Transport settings are informational in Beta4; experimental mesh stays on archived branches.
s = sub_once(
    s,
    r'''    private fun showTransportModeDialog\(\) \{.*?    \}\n\n    private fun showMeshLabRoleDialog''',
    '''    private fun showTransportModeDialog() {\n        transportMode = TransportMode.INTERNET_ONLY\n        meshLabRole = MeshNode.LabRole.NORMAL\n        saveSettings()\n        AlertDialog.Builder(this)\n            .setTitle("Internet voice engine")\n            .setMessage("Beta4 uses Internet-only WebRTC + Opus. Offline / multi-hop modes are not active in this package so voice stability can be tested independently.")\n            .setPositiveButton("OK", null)\n            .show()\n    }\n\n    private fun showMeshLabRoleDialog''',
    'Internet-only transport dialog',
)

s = replace_once(
    s,
    '''    private fun transportModeLabel(): String = when (transportMode) {\n        TransportMode.AUTO -> "AUTO HYBRID"\n        TransportMode.LOCAL_ONLY -> "LOCAL MESH ONLY"\n        TransportMode.INTERNET_ONLY -> "INTERNET ONLY"\n    }''',
    '''    private fun transportModeLabel(): String = "INTERNET • WEBRTC OPUS"''',
    'transport label',
)

# If any old call reaches this method, keep the app pinned to Beta4 Internet voice.
s = sub_once(
    s,
    r'''    private fun applyTransportModeChange\(\) \{.*?    \}\n\n    private fun showSettingsAndHelpDialog''',
    '''    private fun applyTransportModeChange() {\n        transportMode = TransportMode.INTERNET_ONLY\n        meshLabRole = MeshNode.LabRole.NORMAL\n        saveSettings()\n        if (!rideStarted) return\n\n        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }\n        internetNode.stop()\n        internetPeerCount = 0\n        internetNode.start(normalizedRideCode(), rider, deviceLabel())\n        internetNode.setMuted(micMuted)\n        applySelectedAudioRoute()\n        updateTransportStatus()\n        updateCapturePolicy()\n    }\n\n    private fun showSettingsAndHelpDialog''',
    'pin transport change',
)

# Settings: no offline / Max Link decisions.
s = sub_once(
    s,
    r'''    private fun showSettingsAndHelpDialog\(\) \{.*?    \}\n\n    private fun ensureBetaFirstLaunch''',
    '''    private fun showSettingsAndHelpDialog() {\n        AlertDialog.Builder(this)\n            .setTitle("RideMesh Beta4 settings & help")\n            .setMessage(\n                "Voice engine: WebRTC + Opus over Internet\\n\\n" +\n                    "RideMesh automatically yields microphone and playback when a normal phone call, WhatsApp call or another VoIP app takes Android audio focus, then resumes after the call.\\n\\n" +\n                    "Offline / multi-hop is intentionally disabled in this Beta4 package while we prioritize clear, stable group voice.\\n\\n" +\n                    betaStatusSentence() + "\\n\\n" +\n                    "Bug reports: WhatsApp group or direct support +91 9188664823."\n            )\n            .setPositiveButton("VOICE STATUS") { _, _ -> showRideStatusDialog() }\n            .setNeutralButton("ENGINE INFO") { _, _ -> showTransportModeDialog() }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n    private fun ensureBetaFirstLaunch''',
    'Beta4 settings',
)

# Repurpose old Offline Diagnostics action into WebRTC diagnostics so no stale mesh UI remains.
s = sub_once(
    s,
    r'''    private fun showOfflineDiagnosticsDialog\(\) \{.*?    \}\n\n    private fun showRideStatusDialog''',
    '''    private fun showOfflineDiagnosticsDialog() {\n        showRideStatusDialog()\n    }\n\n    private fun showRideStatusDialog''',
    'repurpose offline diagnostics',
)

s = sub_once(
    s,
    r'''    private fun showRideStatusDialog\(\) \{.*?    \}\n\n    private fun openWhatsAppBugReport''',
    '''    private fun showRideStatusDialog() {\n        val diag = internetNode.diagnostics()\n        AlertDialog.Builder(this)\n            .setTitle("Ride status • WebRTC + Opus")\n            .setMessage(\n                "Path: Internet WebRTC\\n" +\n                    "Codec: ${diag.codec}\\n" +\n                    "Signaling: ${if (diag.signalingConnected) "CONNECTED" else "RECONNECTING"}\\n" +\n                    "Known riders: ${diag.knownRiders + 1}\\n" +\n                    "Voice peers connected: ${diag.voicePeersConnected}\\n" +\n                    "SDP offers sent: ${diag.offersSent} • answers: ${diag.answersSent}\\n" +\n                    "ICE candidates sent: ${diag.candidatesSent}\\n" +\n                    "ICE reconnects: ${diag.reconnects}\\n" +\n                    "TURN relay: ${if (diag.turnConfigured) "CONFIGURED" else "NOT CONFIGURED IN THIS BETA"}\\n" +\n                    "Last network error: ${diag.lastError.ifBlank { "none" }}\\n\\n" +\n                    "PEER STATES\\n${diag.peerStates}\\n\\n" +\n                    "Audio: ${binding.audioTile.text}\\n" +\n                    "Microphone: ${if (micMuted) "MUTED" else "LIVE"}\\n" +\n                    "Call-safe audio focus: ON\\n" +\n                    betaStatusSentence()\n            )\n            .setPositiveButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n    private fun openWhatsAppBugReport''',
    'WebRTC ride status',
)

# Add WebRTC diagnostics to direct bug report instead of old mesh measurements.
s = sub_once(
    s,
    r'''            append\("Transport mode: \$\{transportModeLabel\(\)\} • role \$\{meshLabRole\.name\}\\n"\)\n            if \(::meshNode\.isInitialized\) \{.*?            \}\n            append\("Problem: "\)''',
    '''            append("Voice engine: WebRTC + Opus\\n")\n            if (::internetNode.isInitialized) {\n                val d = internetNode.diagnostics()\n                append("WebRTC: signaling=${d.signalingConnected}, voicePeers=${d.voicePeersConnected}, riders=${d.knownRiders}, offers=${d.offersSent}, answers=${d.answersSent}, iceCandidates=${d.candidatesSent}, reconnects=${d.reconnects}, TURN=${d.turnConfigured}, error=${d.lastError.ifBlank { "none" }}\\n")\n                append("Peer states: ${d.peerStates.replace('\\n', ';')}\\n")\n            }\n            append("Problem: ")''',
    'WebRTC bug report',
)

p.write_text(s)


# -----------------------------------------------------------------------------
# Layout copy: preserve approved black/cyan design, remove hybrid/offline claims.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/res/layout/activity_main.xml'
s = p.read_text()
s = s.replace(
    'RideMesh uses the Internet for long-distance connectivity and automatically switches to local mesh when you’re out of coverage.',
    'RideMesh uses low-latency WebRTC Internet voice with Opus for clear group communication across distance.',
)
s = s.replace('android:text="HYBRID"', 'android:text="INTERNET"')
s = s.replace('android:text="Internet + Mesh\nReady"', 'android:text="WebRTC Voice\nReady"')
p.write_text(s)


# -----------------------------------------------------------------------------
# Foreground service copy / type: Beta4 is microphone Internet voice, not mesh.
# Keep connectedDevice in the declared type for Bluetooth helmet routing compatibility.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/service/RideService.kt'
s = p.read_text()
s = s.replace('RideMesh intercom is active', 'RideMesh WebRTC intercom is active')
s = s.replace(
    '// Keep the mesh process alive with the connected-device type instead of',
    '// Keep the ride process alive with the connected-device type instead of',
)
p.write_text(s)

print('Beta4 Internet-only WebRTC UI/runtime patch applied')
