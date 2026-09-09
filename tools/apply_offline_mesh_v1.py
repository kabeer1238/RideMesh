#!/usr/bin/env python3
from pathlib import Path

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
manifest = Path("app/src/main/AndroidManifest.xml")

s = main.read_text()

# Import the experimental controller without disturbing the production transports.
if "import com.bikemesh.ridemesh.offline.OfflineMeshController" not in s:
    anchor = "import com.bikemesh.ridemesh.mesh.MeshNode\n"
    if anchor not in s:
        raise SystemExit("Offline mesh patch: MeshNode import anchor not found")
    s = s.replace(
        anchor,
        anchor + "import com.bikemesh.ridemesh.offline.OfflineMeshController\n",
        1,
    )

# Controller lifetime is tied to MainActivity/active ride for Phase 1.
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
        "            runOnUiThread { log(message) }\n"
        "        }\n\n"
    )
    s = s.replace(anchor, init + anchor, 1)

# Wi-Fi Aware permission changed in Android 13. Keep location only on <= Android 12L.
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

# Start the experimental link alongside the existing production transports.
# It does not carry production voice yet; Phase 1 is discovery/data-path/RTT validation.
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

main.write_text(s)

m = manifest.read_text()

feature = '    <uses-feature android:name="android.hardware.wifi.aware" android:required="false" />\n'
if "android.hardware.wifi.aware" not in m:
    manifest_anchor = "<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\">\n"
    if manifest_anchor not in m:
        raise SystemExit("Offline mesh patch: manifest root anchor not found")
    m = m.replace(manifest_anchor, manifest_anchor + "\n" + feature, 1)

permissions = [
    '    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />',
    '    <uses-permission android:name="android.permission.CHANGE_WIFI_STATE" />',
    '    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" android:maxSdkVersion="32" />',
    '    <uses-permission android:name="android.permission.NEARBY_WIFI_DEVICES" android:usesPermissionFlags="neverForLocation" />',
]

application_anchor = "    <application\n"
if application_anchor not in m:
    raise SystemExit("Offline mesh patch: application anchor not found")

missing = [line for line in permissions if line not in m]
if missing:
    m = m.replace(
        application_anchor,
        "\n".join(missing) + "\n\n" + application_anchor,
        1,
    )

manifest.write_text(m)
print("Offline mesh v1 Android Wi-Fi Aware integration applied")
