#!/usr/bin/env python3
from pathlib import Path

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
manifest = Path("app/src/main/AndroidManifest.xml")

s = main.read_text()

# Import the dedicated offline controller without disturbing the production files.
if "import com.bikemesh.ridemesh.offline.OfflineMeshController" not in s:
    anchor = "import com.bikemesh.ridemesh.mesh.MeshNode\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: MeshNode import anchor not found")
    s = s.replace(
        anchor,
        anchor + "import com.bikemesh.ridemesh.offline.OfflineMeshController\n",
        1,
    )

if "private lateinit var offlineMeshController: OfflineMeshController" not in s:
    anchor = "    private lateinit var audioEngine: AudioEngine\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: audioEngine property anchor not found")
    s = s.replace(
        anchor,
        anchor + "    private lateinit var offlineMeshController: OfflineMeshController\n",
        1,
    )

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

# Android 13+ LocalOnlyHotspot and Wi-Fi Aware use NEARBY_WIFI_DEVICES.
if "Manifest.permission.NEARBY_WIFI_DEVICES" not in s:
    anchor = "    private fun requiredPermissions(): List<String> = buildList {\n        add(Manifest.permission.RECORD_AUDIO)\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: requiredPermissions anchor not found")
    permission_block = (
        "    private fun requiredPermissions(): List<String> = buildList {\n"
        "        add(Manifest.permission.RECORD_AUDIO)\n"
        "        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {\n"
        "            add(Manifest.permission.NEARBY_WIFI_DEVICES)\n"
        "        } else {\n"
        "            add(Manifest.permission.ACCESS_FINE_LOCATION)\n"
        "        }\n"
    )
    s = s.replace(anchor, permission_block, 1)

# Start the Android-hosted local-only Wi-Fi link when the ride begins.
if "offlineMeshController.start(rider, code)" not in s:
    anchor = "            rideStarted = true\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: rideStarted anchor not found")
    s = s.replace(
        anchor,
        anchor + "            offlineMeshController.start(rider, code)\n",
        1,
    )

if "offlineMeshController.stop()\n        audioEngine.stopTransmit()" not in s:
    anchor = "        stopLobbyDiscovery()\n        audioEngine.stopTransmit()\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: stopRide anchor not found")
    s = s.replace(
        anchor,
        "        stopLobbyDiscovery()\n        offlineMeshController.stop()\n        audioEngine.stopTransmit()\n",
        1,
    )

if "if (::offlineMeshController.isInitialized) offlineMeshController.stop()" not in s:
    anchor = "        if (::lobbyNode.isInitialized) lobbyNode.stop()\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: onDestroy lobby anchor not found")
    s = s.replace(
        anchor,
        anchor + "        if (::offlineMeshController.isInitialized) offlineMeshController.stop()\n",
        1,
    )

# During an active offline test ride, the existing INVITE QR becomes the Android
# LocalOnlyHotspot credential payload. Before a ride it remains the normal ride QR.
normal_qr = '        val payload = "ridemesh://join?ride=${Uri.encode(code)}"\n'
offline_qr = (
    '        val payload = if (rideStarted && ::offlineMeshController.isInitialized) {\n'
    '            offlineMeshController.hotspotInvitePayload() ?: "ridemesh://join?ride=${Uri.encode(code)}"\n'
    '        } else {\n'
    '            "ridemesh://join?ride=${Uri.encode(code)}"\n'
    '        }\n'
)
if normal_qr in s:
    s = s.replace(normal_qr, offline_qr, 1)
elif "offlineMeshController.hotspotInvitePayload()" not in s:
    raise SystemExit("Offline mesh patch: QR payload anchor not found")

# Make the active screen describe the real offline path rather than the old
# Internet/WebRTC state. The production branch is untouched; this is test-only.
status_anchor = "    private fun updateTransportStatus() {\n        if (!rideStarted) return\n"
if status_anchor in s and "OFFLINE HOTSPOT" not in s:
    offline_status = (
        "    private fun updateTransportStatus() {\n"
        "        if (!rideStarted) return\n"
        "        if (::offlineMeshController.isInitialized) {\n"
        "            val offlinePeers = offlineMeshController.connectedPeerCount()\n"
        "            val offlineReady = offlineMeshController.hotspotInvitePayload() != null\n"
        "            if (offlinePeers > 0 || offlineReady) {\n"
        "                binding.networkTile.text = if (offlinePeers > 0) \"OFFLINE\" else \"HOTSPOT\"\n"
        "                binding.riderCount.text = \"RIDE ACTIVE\"\n"
        "                binding.meshStatus.text = if (offlinePeers > 0) {\n"
        "                    val peer = offlineMeshController.connectedPeerName() ?: \"IPHONE\"\n"
        "                    val rtt = offlineMeshController.currentRttMs()?.let { \" • ${it}ms\" }.orEmpty()\n"
        "                    \"OFFLINE CONNECTED • $peer$rtt\"\n"
        "                } else {\n"
        "                    \"OFFLINE HOTSPOT READY • INVITE → SHOW QR\"\n"
        "                }\n"
        "                binding.homeNetworkStatus.text = if (offlinePeers > 0) \"Offline Link\\nConnected\" else \"Offline Link\\nReady\"\n"
        "                binding.activeRiders.text = \"RIDERS ${offlinePeers + 1}\"\n"
        "                renderRiderGrid()\n"
        "                applyPowerUi()\n"
        "                return\n"
        "            }\n"
        "        }\n"
    )
    s = s.replace(status_anchor, offline_status, 1)
elif "OFFLINE HOTSPOT READY" not in s:
    raise SystemExit("Offline mesh patch: updateTransportStatus anchor not found")

main.write_text(s)

m = manifest.read_text()

feature = '    <uses-feature android:name="android.hardware.wifi.aware" android:required="false" />\n'
if "android.hardware.wifi.aware" not in m:
    manifest_anchor = "<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">\n"
    if manifest_anchor not in m:
        raise SystemExit("Offline mesh patch: manifest root anchor not found")
    m = m.replace(manifest_anchor, manifest_anchor + "\n" + feature, 1)

# Production vc25 already declares some permissions. Add local Wi-Fi permissions
# by permission NAME so manifest merger never sees duplicates.
permissions = [
    (
        "android.permission.ACCESS_WIFI_STATE",
        '    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />',
    ),
    (
        "android.permission.CHANGE_WIFI_STATE",
        '    <uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />',
    ),
    (
        "android.permission.ACCESS_FINE_LOCATION",
        '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" android:maxSdkVersion="32" />',
    ),
    (
        "android.permission.NEARBY_WIFI_DEVICES",
        '    <uses-permission android:name="android.permission.NEARBY_WIFI_DEVICES" android:usesPermissionFlags="neverForLocation" />',
    ),
]

application_anchor = "    <application\n"
if application_anchor not in m:
    raise SystemExit("Offline mesh patch: application anchor not found")

missing = [line for permission_name, line in permissions if permission_name not in m]
if missing:
    m = m.replace(
        application_anchor,
        "\n".join(missing) + "\n\n" + application_anchor,
        1,
    )

manifest.write_text(m)
print("Offline Android<->iPhone LocalOnlyHotspot + Bonjour integration applied")
