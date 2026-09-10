#!/usr/bin/env python3
from pathlib import Path

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
manifest = Path("app/src/main/AndroidManifest.xml")
s = main.read_text()

# Offline is additive: import/controller hooks only. Existing Internet/WebRTC and
# Maps code is left in place and production branch is never modified by this job.
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

if "OfflineMeshController(applicationContext)" not in s:
    anchor = "        applySelectedAudioRoute()\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: applySelectedAudioRoute anchor not found")
    init = (
        "        offlineMeshController = OfflineMeshController(applicationContext) { message ->\n"
        "            runOnUiThread {\n"
        "                log(message)\n"
        "                if (rideStarted) updateTransportStatus()\n"
        "            }\n"
        "        }\n\n"
    )
    s = s.replace(anchor, init + anchor, 1)

# JOIN must never show a newly-created code. It may offer only the last ACTIVE
# ride code. CREATE RIDE remains the only action that generates a fresh code.
old_join = (
    "        binding.joinRide.setOnClickListener {\n"
    "            if (!ensureBetaUsable()) return@setOnClickListener\n"
    "            binding.setupTitle.text = \"JOIN RIDE\"\n"
    "            showScreen(Screen.SETUP)\n"
    "            binding.rideCode.requestFocus()\n"
    "        }\n"
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
    "        }\n"
)
if old_join in s:
    s = s.replace(old_join, new_join, 1)
elif 'prefs.getString("last_active_ride_code"' not in s:
    raise SystemExit("Offline mesh patch: JOIN button anchor not found")

# Remember the most recent ride only after the rider actually starts it. This
# makes the JOIN prefill a real rejoin convenience rather than a random code.
if 'putString("last_active_ride_code", code)' not in s:
    anchor = "        saveSettings()\n\n        try {\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: startRide saveSettings anchor not found")
    s = s.replace(
        anchor,
        "        saveSettings()\n        prefs.edit().putString(\"last_active_ride_code\", code).apply()\n\n        try {\n",
        1,
    )

# Nearby Connections on modern Android needs nearby Wi-Fi + Bluetooth runtime
# permissions. Android <=12 keeps the location permission used by discovery.
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

# Start Nearby P2P_CLUSTER only after the ride itself has successfully entered
# active state. No LocalOnlyHotspot/AndroidShare is created by the controller.
if "offlineMeshController.start(rider, code)" not in s:
    anchor = "            rideStarted = true\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: rideStarted anchor not found")
    s = s.replace(anchor, anchor + "            offlineMeshController.start(rider, code)\n", 1)

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

# QR remains a simple RideMesh ride-code QR. It is NOT a hotspot credential QR.
# This keeps manual code entry and QR scanning equivalent.

# Surface the Nearby state without deleting the original online status logic.
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
        "                \"OFFLINE P2P_CLUSTER CONNECTED • $peer$rtt\"\n"
        "            } else {\n"
        "                \"OFFLINE P2P_CLUSTER • SEARCHING SAME-CODE RIDERS\"\n"
        "            }\n"
        "            binding.homeNetworkStatus.text = if (offlinePeers > 0) \"Offline Mesh\\nConnected\" else \"Offline Mesh\\nSearching\"\n"
        "            binding.activeRiders.text = \"RIDERS ${offlinePeers + 1}\"\n"
        "            renderRiderGrid()\n"
        "            applyPowerUi()\n"
        "            return\n"
        "        }\n"
    )
    s = s.replace(status_anchor, block, 1)
elif "OFFLINE P2P_CLUSTER" not in s:
    raise SystemExit("Offline mesh patch: updateTransportStatus anchor not found")

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

print("Offline Nearby P2P_CLUSTER integration applied; online mesh and Maps preserved")
