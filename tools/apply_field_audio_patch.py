from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected marker not found in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Build identity for the next field-test APK.
replace_once(
    "app/build.gradle.kts",
    'versionCode = 13\n        versionName = "0.4.3-beta1.1"',
    'versionCode = 14\n        versionName = "0.4.4-beta1.1"',
)

# Use the actual RideMesh artwork directly as the installed launcher icon.
replace_once(
    "app/src/main/AndroidManifest.xml",
    'android:icon="@mipmap/ic_launcher"\n        android:roundIcon="@mipmap/ic_launcher_round"',
    'android:icon="@drawable/ridemesh_icon"\n        android:roundIcon="@drawable/ridemesh_icon"',
)

# Preserve the remote rider/node ID all the way into the audio mixer.
replace_once(
    "app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt",
    'fun onInternetAudio(audio: ByteArray)',
    'fun onInternetAudio(sourceId: String, audio: ByteArray)',
)
replace_once(
    "app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt",
    'listener.onInternetAudio(packet.audio)',
    'listener.onInternetAudio(packet.origin.toString(), packet.audio)',
)

# MainActivity audio callbacks now give AudioEngine the remote source ID.
replace_once(
    "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt",
    '''    override fun onAudioPacket(audio: ByteArray) {\n        if (rideStarted) audioEngine.playIncoming(audio)\n    }''',
    '''    override fun onAudioPacket(sourceId: String, audio: ByteArray) {\n        if (rideStarted) audioEngine.playIncoming(sourceId, audio)\n    }''',
)
replace_once(
    "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt",
    '''    override fun onInternetAudio(audio: ByteArray) {\n        if (rideStarted) audioEngine.playIncoming(audio)\n    }''',
    '''    override fun onInternetAudio(sourceId: String, audio: ByteArray) {\n        if (rideStarted) audioEngine.playIncoming(sourceId, audio)\n    }''',
)

# Keep a real rider-name preview directly on the active ride screen.
replace_once(
    "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt",
    '''        binding.activeRiders.text = "RIDERS $visibleRiderTotal"\n        applyPowerUi()''',
    '''        binding.activeRiders.text = "RIDERS $visibleRiderTotal"\n        updateRiderRosterPreview()\n        applyPowerUi()''',
)

marker = '''    private fun applyPowerUi() {'''
method = '''    private fun updateRiderRosterPreview() {\n        if (!rideStarted) return\n\n        val me = binding.riderName.text?.toString().orEmpty().ifBlank { Build.MODEL.take(18) }\n        val names = linkedSetOf<String>()\n        names.add(me)\n\n        if (internetNode.isConnected()) {\n            internetNode.remotePeers().forEach { names.add(it.displayName) }\n        } else if (meshRunning) {\n            meshNode.directPeers().forEach { names.add(it.displayName) }\n        }\n\n        binding.activeRiderNames.text = names.joinToString("   •   ")\n    }\n\n'''
replace_once(
    "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt",
    marker,
    method + marker,
)
replace_once(
    "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt",
    'binding.activeRiders.text = "RIDERS"\n        log("Ride stopped")',
    'binding.activeRiders.text = "RIDERS"\n        binding.activeRiderNames.text = ""\n        log("Ride stopped")',
)

# Make the selected RideMesh logo visible in the active ride header.
replace_once(
    "app/src/main/res/layout/activity_main.xml",
    '''            <ImageView\n                android:layout_width="40dp"\n                android:layout_height="40dp"\n                android:contentDescription="Ride Mesh"\n                android:src="@drawable/ridemesh_icon" />''',
    '''            <ImageView\n                android:layout_width="112dp"\n                android:layout_height="42dp"\n                android:contentDescription="RideMesh by Autopilot India"\n                android:scaleType="centerInside"\n                android:src="@drawable/ridemesh_logo" />''',
)

mesh_status = '''        <TextView\n            android:id="@+id/meshStatus"\n            android:layout_width="match_parent"\n            android:layout_height="wrap_content"\n            android:layout_marginTop="8dp"\n            android:gravity="center"\n            android:text="CONNECTING…"\n            android:textColor="@color/accent"\n            android:textSize="12sp"\n            android:textStyle="bold" />'''
rider_preview = mesh_status + '''\n\n        <TextView\n            android:id="@+id/activeRiderNames"\n            android:layout_width="match_parent"\n            android:layout_height="wrap_content"\n            android:layout_marginTop="10dp"\n            android:background="@drawable/panel_bg"\n            android:gravity="center"\n            android:maxLines="3"\n            android:paddingStart="12dp"\n            android:paddingTop="9dp"\n            android:paddingEnd="12dp"\n            android:paddingBottom="9dp"\n            android:text=""\n            android:textColor="@color/white_soft"\n            android:textSize="11sp"\n            android:textStyle="bold" />'''
replace_once("app/src/main/res/layout/activity_main.xml", mesh_status, rider_preview)

# Update InternetNode test listener for source-aware audio callback.
replace_once(
    "app/src/test/java/com/bikemesh/ridemesh/transport/InternetNodeTest.kt",
    'override fun onInternetAudio(audio: ByteArray) = Unit',
    'override fun onInternetAudio(sourceId: String, audio: ByteArray) = Unit',
)

print("RideMesh field audio/icon/roster patch applied")
