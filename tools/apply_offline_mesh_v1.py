#!/usr/bin/env python3
from pathlib import Path
import re

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
manifest = Path("app/src/main/AndroidManifest.xml")
s = main.read_text()

if "import com.bikemesh.ridemesh.offline.OfflineMeshController" not in s:
    anchor = "import com.bikemesh.ridemesh.mesh.MeshNode\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: MeshNode import anchor not found")
    s = s.replace(anchor, anchor + "import com.bikemesh.ridemesh.offline.OfflineMeshController\n", 1)

if "private lateinit var offlineMeshController: OfflineMeshController" not in s:
    anchor = "    private lateinit var audioEngine: AudioEngine\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: audioEngine property anchor not found")
    s = s.replace(anchor, anchor + "    private lateinit var offlineMeshController: OfflineMeshController\n", 1)

if "OfflineMeshController(applicationContext" not in s:
    anchor = "        applySelectedAudioRoute()\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: applySelectedAudioRoute anchor not found")
    init = (
        "        offlineMeshController = OfflineMeshController(\n"
        "            context = applicationContext,\n"
        "            onLog = { message ->\n"
        "                runOnUiThread {\n"
        "                    log(message)\n"
        "                    if (rideStarted) updateTransportStatus()\n"
        "                }\n"
        "            },\n"
        "            onAudioFrame = { sourceNodeId, sequence, timestampMs, pcm ->\n"
        "                markRiderSpeaking(\"offline:$sourceNodeId\")\n"
        "                audioEngine.playIncoming(sourceNodeId, sequence, timestampMs, pcm)\n"
        "            },\n"
        "        )\n\n"
    )
    s = s.replace(anchor, init + anchor, 1)

if 'prefs.getString("last_active_ride_code"' not in s:
    join_re = re.compile(
        r'        binding\.joinRide\.setOnClickListener \{.*?\n        \}\n\n(?=        binding\.backHome)',
        re.S,
    )
    new_join = (
        "        binding.joinRide.setOnClickListener {\n"
        "            if (!ensureBetaUsable()) return@setOnClickListener\n"
        "            binding.setupTitle.text = \"JOIN RIDE\"\n"
        "            val lastRide = prefs.getString(\"last_active_ride_code\", \"\").orEmpty()\n"
        "            binding.rideCode.setText(lastRide)\n"
        "            showScreen(Screen.SETUP)\n"
        "            binding.rideCode.requestFocus()\n"
        "            binding.rideCode.setSelection(binding.rideCode.text?.length ?: 0)\n"
        "        }\n\n"
    )
    s, count = join_re.subn(new_join, s, count=1)
    if count != 1:
        raise SystemExit("Offline mesh patch: JOIN listener not found after production UI materialization")

if 'putString("last_active_ride_code", code)' not in s:
    anchor = "        saveSettings()\n\n        try {\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: startRide saveSettings anchor not found")
    s = s.replace(anchor, "        saveSettings()\n        prefs.edit().putString(\"last_active_ride_code\", code).apply()\n\n        try {\n", 1)

if "Manifest.permission.NEARBY_WIFI_DEVICES" not in s:
    anchor = "    private fun requiredPermissions(): List<String> = buildList {\n        add(Manifest.permission.RECORD_AUDIO)\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: requiredPermissions anchor not found")
    block = (
        "    private fun requiredPermissions(): List<String> = buildList {\n"
        "        add(Manifest.permission.RECORD_AUDIO)\n"
        "        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {\n"
        "            add(Manifest.permission.NEARBY_WIFI_DEVICES)\n"
        "        } else {\n"
        "            add(Manifest.permission.ACCESS_FINE_LOCATION)\n"
        "        }\n"
    )
    s = s.replace(anchor, block, 1)

if "Manifest.permission.BLUETOOTH_ADVERTISE" not in s:
    anchor = (
        "        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {\n"
        "            add(Manifest.permission.NEARBY_WIFI_DEVICES)\n"
        "        } else {\n"
        "            add(Manifest.permission.ACCESS_FINE_LOCATION)\n"
        "        }\n"
    )
    if anchor not in s:
        raise SystemExit("Offline mesh patch: nearby permission anchor not found")
    s = s.replace(
        anchor,
        anchor +
        "        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {\n" +
        "            add(Manifest.permission.BLUETOOTH_SCAN)\n" +
        "            add(Manifest.permission.BLUETOOTH_ADVERTISE)\n" +
        "            add(Manifest.permission.BLUETOOTH_CONNECT)\n" +
        "        }\n",
        1,
    )

# Dedicated offline field build: keep WebRTC from competing for the microphone
# while Nearby voice quality is being tuned. Production online code is untouched.
webrtc_start = (
    "            internetNode.start(code, rider, deviceLabel())\n"
    "            internetNode.setMuted(micMuted)\n"
    "            applySelectedAudioRoute()\n"
)
if webrtc_start in s:
    s = s.replace(
        webrtc_start,
        "            // OFFLINE TEST BUILD: WebRTC audio intentionally not started.\n"
        "            // Nearby + AudioEngine exclusively own this voice test.\n"
        "            applySelectedAudioRoute()\n",
        1,
    )

if "offlineMeshController.start(rider, code" not in s:
    anchor = "            rideStarted = true\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: rideStarted anchor not found")
    s = s.replace(
        anchor,
        anchor +
        "            offlineMeshController.start(rider, code, deviceLabel())\n"
        "            audioEngine.setUserMuted(micMuted)\n"
        "            audioEngine.startTransmit()\n",
        1,
    )

old_send = (
    "    private fun sendHybridAudio(audio: ByteArray) {\n"
    "        // Beta4 does not send PCM frames from this legacy engine. WebRTC owns voice capture.\n"
    "    }\n"
)
new_send = (
    "    private fun sendHybridAudio(audio: ByteArray) {\n"
    "        if (::offlineMeshController.isInitialized && offlineMeshController.isActive()) {\n"
    "            offlineMeshController.sendAudioFrame(audio)\n"
    "        }\n"
    "    }\n"
)
if old_send in s:
    s = s.replace(old_send, new_send, 1)
elif "offlineMeshController.sendAudioFrame(audio)" not in s:
    raise SystemExit("Offline mesh patch: sendHybridAudio anchor not found")

if "offlineMeshController.stop()\n        audioEngine.stopTransmit()" not in s:
    anchor = "        stopLobbyDiscovery()\n        audioEngine.stopTransmit()\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: stopRide anchor not found")
    s = s.replace(anchor, "        stopLobbyDiscovery()\n        offlineMeshController.stop()\n        audioEngine.stopTransmit()\n", 1)

if "if (::offlineMeshController.isInitialized) offlineMeshController.stop()" not in s:
    anchor = "        if (::lobbyNode.isInitialized) lobbyNode.stop()\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: onDestroy anchor not found")
    s = s.replace(anchor, anchor + "        if (::offlineMeshController.isInitialized) offlineMeshController.stop()\n", 1)

status_anchor = "    private fun updateTransportStatus() {\n        if (!rideStarted) return\n"
if status_anchor in s and "OFFLINE P2P_CLUSTER" not in s:
    block = (
        "    private fun updateTransportStatus() {\n"
        "        if (!rideStarted) return\n"
        "        if (::offlineMeshController.isInitialized && offlineMeshController.isActive()) {\n"
        "            val offlinePeers = offlineMeshController.connectedPeerCount()\n"
        "            binding.networkTile.text = if (offlinePeers > 0) \"OFFLINE\" else \"MESH\"\n"
        "            binding.riderCount.text = \"RIDE ACTIVE\"\n"
        "            binding.meshStatus.text = if (offlinePeers > 0) {\n"
        "                val peer = offlineMeshController.connectedPeerName() ?: \"ANDROID RIDER\"\n"
        "                val rtt = offlineMeshController.currentRttMs()?.let { \" • ${it}ms\" }.orEmpty()\n"
        "                val tx = offlineMeshController.audioTxCount()\n"
        "                val rx = offlineMeshController.audioRxCount()\n"
        "                \"OFFLINE P2P_CLUSTER CONNECTED • $peer$rtt • VOICE TX $tx RX $rx\"\n"
        "            } else {\n"
        "                \"OFFLINE P2P_CLUSTER • ${offlineMeshController.diagnosticSummary()}\"\n"
        "            }\n"
        "            binding.homeNetworkStatus.text = if (offlinePeers > 0) \"Offline Mesh\\nVoice Test\" else \"Offline Mesh\\nDiagnosing\"\n"
        "            binding.activeRiders.text = \"RIDERS ${offlinePeers + 1}\"\n"
        "            renderRiderGrid()\n"
        "            applyPowerUi()\n"
        "            return\n"
        "        }\n"
    )
    s = s.replace(status_anchor, block, 1)
elif "OFFLINE P2P_CLUSTER" not in s:
    raise SystemExit("Offline mesh patch: updateTransportStatus anchor not found")

old_mute = "        if (::internetNode.isInitialized) internetNode.setMuted(muted)\n"
if old_mute in s and "audioEngine.setUserMuted(muted)" not in s:
    s = s.replace(
        old_mute,
        old_mute + "        if (::audioEngine.isInitialized) audioEngine.setUserMuted(muted)\n",
        1,
    )

policy_start = "    private fun updateCapturePolicy() {\n        if (!rideStarted) return\n"
if policy_start in s and "OFFLINE VOICE ACTIVE" not in s:
    replacement = (
        "    private fun updateCapturePolicy() {\n"
        "        if (!rideStarted) return\n"
        "        if (::offlineMeshController.isInitialized && offlineMeshController.isActive()) {\n"
        "            updateAudioUi(if (micMuted) \"MIC MUTED • LISTENING ONLY\" else \"OFFLINE VOICE ACTIVE • MIC + JITTER BUFFER\")\n"
        "            return\n"
        "        }\n"
    )
    s = s.replace(policy_start, replacement, 1)

# Populate the main rider grid from the live Nearby identity table, so every
# Android device sees the other rider's real name, device and link state.
self_old = (
    "                qualityBars = if (internetNode.isConnected() || directPeerCount > 0) 4 else 1,\n"
    "                path = if (internetNode.isConnected()) \"Internet\" else if (directPeerCount > 0) \"Local\" else \"Searching\",\n"
)
self_new = (
    "                qualityBars = if (::offlineMeshController.isInitialized && offlineMeshController.connectedPeerCount() > 0) 4 else if (internetNode.isConnected() || directPeerCount > 0) 4 else 1,\n"
    "                path = when {\n"
    "                    ::offlineMeshController.isInitialized && offlineMeshController.connectedPeerCount() > 0 -> \"Offline Nearby\"\n"
    "                    internetNode.isConnected() -> \"Internet\"\n"
    "                    directPeerCount > 0 -> \"Local\"\n"
    "                    else -> \"Searching\"\n"
    "                },\n"
)
if self_old in s:
    s = s.replace(self_old, self_new, 1)

remote_anchor = (
    "        if (internetNode.isConnected()) {\n"
    "            internetNode.remotePeers().forEach { peer ->\n"
)
if remote_anchor in s and "offlineMeshController.connectedPeerDetails().forEach" not in s:
    remote_block = (
        "        if (::offlineMeshController.isInitialized && offlineMeshController.isActive() && offlineMeshController.connectedPeerCount() > 0) {\n"
        "            offlineMeshController.connectedPeerDetails().forEach { peer ->\n"
        "                val bars = when {\n"
        "                    peer.rttMs == null -> 3\n"
        "                    peer.rttMs <= 120 -> 4\n"
        "                    peer.rttMs <= 250 -> 3\n"
        "                    peer.rttMs <= 450 -> 2\n"
        "                    else -> 1\n"
        "                }\n"
        "                riders += RiderTile(\n"
        "                    key = \"offline:${peer.nodeId}\",\n"
        "                    name = peer.riderName,\n"
        "                    device = peer.deviceName,\n"
        "                    qualityBars = bars,\n"
        "                    path = peer.rttMs?.let { \"Offline Nearby • ${it}ms\" } ?: \"Offline Nearby\",\n"
        "                )\n"
        "            }\n"
        "        } else if (internetNode.isConnected()) {\n"
        "            internetNode.remotePeers().forEach { peer ->\n"
    )
    s = s.replace(remote_anchor, remote_block, 1)

# Show device + transport under each rider name instead of hiding those fields.
height_old = "                height = dp(136)\n"
if height_old in s and "height = dp(158)" not in s:
    s = s.replace(height_old, "                height = dp(158)\n", 1)

quality_anchor = (
    "        val quality = TextView(this).apply {\n"
    "            text = if (rider.self) \"YOU  ${qualityGlyphs(rider.qualityBars)}\" else qualityGlyphs(rider.qualityBars)\n"
)
if quality_anchor in s and "val riderDetail = TextView(this).apply" not in s:
    detail_block = (
        "        val riderDetail = TextView(this).apply {\n"
        "            text = if (rider.self) rider.device else \"${rider.device} • ${rider.path}\"\n"
        "            gravity = Gravity.CENTER\n"
        "            maxLines = 1\n"
        "            ellipsize = android.text.TextUtils.TruncateAt.END\n"
        "            textSize = 9.5f\n"
        "            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))\n"
        "        }\n"
        "        card.addView(riderDetail, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(20)))\n\n"
    )
    s = s.replace(quality_anchor, detail_block + quality_anchor, 1)

# The RIDERS dialog now uses the same Nearby peer identities and per-peer RTT.
dialog_anchor = (
    "        val internetPeers = if (internetNode.isConnected()) internetNode.remotePeers() else emptyList()\n"
    "        val localPeers = if (meshRunning) meshNode.directPeers() else emptyList()\n"
    "        val riderLines = linkedMapOf<String, String>()\n\n"
)
if dialog_anchor in s and "val offlinePeers = if (::offlineMeshController.isInitialized" not in s:
    dialog_replacement = (
        "        val offlinePeers = if (::offlineMeshController.isInitialized && offlineMeshController.isActive()) offlineMeshController.connectedPeerDetails() else emptyList()\n"
        "        val internetPeers = if (internetNode.isConnected()) internetNode.remotePeers() else emptyList()\n"
        "        val localPeers = if (meshRunning) meshNode.directPeers() else emptyList()\n"
        "        val riderLines = linkedMapOf<String, String>()\n\n"
        "        offlinePeers.forEach { peer ->\n"
        "            val device = peer.deviceName.ifBlank { \"Android device\" }\n"
        "            val rtt = peer.rttMs?.let { \" • ${it}ms RTT\" }.orEmpty()\n"
        "            val key = \"${peer.riderName}|$device\".lowercase(Locale.ROOT)\n"
        "            riderLines[key] = \"• ${peer.riderName}\\n  $device • Offline Nearby$rtt\"\n"
        "        }\n\n"
    )
    s = s.replace(dialog_anchor, dialog_replacement, 1)

path_old = (
    "                when {\n"
    "                    internetNode.isConnected() -> \"Internet\"\n"
    "                    directPeerCount > 0 -> \"Local mesh\"\n"
    "                    else -> \"Reconnecting\"\n"
    "                }\n"
)
path_new = (
    "                when {\n"
    "                    ::offlineMeshController.isInitialized && offlineMeshController.connectedPeerCount() > 0 -> \"Offline Nearby\"\n"
    "                    internetNode.isConnected() -> \"Internet\"\n"
    "                    directPeerCount > 0 -> \"Local mesh\"\n"
    "                    else -> \"Reconnecting\"\n"
    "                }\n"
)
if path_old in s:
    s = s.replace(path_old, path_new, 1)

main.write_text(s)

m = manifest.read_text()
feature = '    <uses-feature android:name="android.hardware.bluetooth_le" android:required="false" />\n'
if "android.hardware.bluetooth_le" not in m:
    root = "<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">\n"
    if root not in m:
        raise SystemExit("Offline mesh patch: manifest root anchor not found")
    m = m.replace(root, root + "\n" + feature, 1)

permissions = [
    ("android.permission.ACCESS_WIFI_STATE", '    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />'),
    ("android.permission.CHANGE_WIFI_STATE", '    <uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />'),
    ("android.permission.ACCESS_FINE_LOCATION", '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" android:maxSdkVersion="32" />'),
    ("android.permission.NEARBY_WIFI_DEVICES", '    <uses-permission android:name="android.permission.NEARBY_WIFI_DEVICES" android:usesPermissionFlags="neverForLocation" />'),
    ("android.permission.BLUETOOTH_SCAN", '    <uses-permission android:name="android.permission.BLUETOOTH_SCAN" android:usesPermissionFlags="neverForLocation" />'),
    ("android.permission.BLUETOOTH_ADVERTISE", '    <uses-permission android:name="android.permission.BLUETOOTH_ADVERTISE" />'),
    ("android.permission.BLUETOOTH_CONNECT", '    <uses-permission android:name="android.permission.BLUETOOTH_CONNECT" />'),
]
application_anchor = "    <application\n"
if application_anchor not in m:
    raise SystemExit("Offline mesh patch: application anchor not found")
missing = [line for name, line in permissions if name not in m]
if missing:
    m = m.replace(application_anchor, "\n".join(missing) + "\n\n" + application_anchor, 1)
manifest.write_text(m)

print("Offline Nearby voice + live rider identity/details applied; production online code preserved")
