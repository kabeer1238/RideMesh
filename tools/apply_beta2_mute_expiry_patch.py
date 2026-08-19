from pathlib import Path

root = Path(".")
layout_path = root / "app/src/main/res/layout/activity_main.xml"
activity_path = root / "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt"
build_path = root / "app/build.gradle.kts"

build_text = build_path.read_text()
layout = layout_path.read_text()
activity = activity_path.read_text()

if 'versionName = "1.0.0-beta2"' not in build_text:
    raise SystemExit("Expected RideMesh 1.0.0-beta2 source before applying approved UI")
if 'android:id="@+id/activeMute"' not in layout:
    raise SystemExit("Expected Beta2 mute control before applying approved UI")

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"{label} anchor not found")
    return text.replace(old, new, 1)

# HOME — match the approved black/cyan reference more closely.
layout = replace_once(
    layout,
    'android:text="Talk naturally while you ride. RideMesh uses Internet for distance and local mesh as the fallback when coverage disappears."',
    'android:text="RideMesh uses the Internet for long-distance connectivity and automatically switches to local mesh when you’re out of coverage."',
    "home hero description",
)

layout = replace_once(
    layout,
    '''                    android:text="JOIN A RIDE"
                    android:textColor="@color/white"
                    android:textSize="11sp"''',
    '''                    android:text="JOIN A RIDE"
                    android:textColor="@color/accent"
                    android:textSize="11sp"''',
    "join ride cyan label",
)

# Add the short cyan underline beneath the hero title, as in the approved reference.
hero_title_end = '''                    android:textColor="@color/white"
                    android:textSize="31sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"'''
hero_title_new = '''                    android:textColor="@color/white"
                    android:textSize="34sp"
                    android:textStyle="bold" />

                <View
                    android:layout_width="34dp"
                    android:layout_height="2dp"
                    android:layout_marginTop="14dp"
                    android:background="@color/accent" />

                <TextView
                    android:layout_width="match_parent"'''
layout = replace_once(layout, hero_title_end, hero_title_new, "hero underline")

# Replace the old status card with the approved READY TO RIDE three-column panel.
status_start = layout.find('''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="22dp"
                android:background="@drawable/status_card_bg"
                android:orientation="vertical"
                android:padding="18dp">

                <TextView
                    android:id="@+id/homeNetworkStatus"''')
footer_start = layout.find('''            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="16dp"
                android:gravity="center"
                android:lineSpacingExtra="2dp"
                android:text="Configure while stopped''')
if status_start < 0 or footer_start < 0 or footer_start <= status_start:
    raise SystemExit("READY TO RIDE card anchors not found")

new_status = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="22dp"
                android:background="@drawable/status_card_bg"
                android:orientation="vertical"
                android:paddingStart="18dp"
                android:paddingTop="18dp"
                android:paddingEnd="18dp"
                android:paddingBottom="16dp">

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:fontFamily="sans-serif-condensed"
                    android:letterSpacing="0.04"
                    android:text="READY TO RIDE"
                    android:textColor="@color/white"
                    android:textSize="16sp"
                    android:textStyle="bold" />

                <View
                    android:layout_width="26dp"
                    android:layout_height="2dp"
                    android:layout_marginTop="10dp"
                    android:background="@color/accent" />

                <LinearLayout
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="18dp"
                    android:gravity="center"
                    android:orientation="horizontal">

                    <LinearLayout
                        android:layout_width="0dp"
                        android:layout_height="wrap_content"
                        android:layout_weight="1"
                        android:gravity="center"
                        android:orientation="vertical"
                        android:paddingHorizontal="4dp">

                        <TextView
                            android:layout_width="wrap_content"
                            android:layout_height="wrap_content"
                            android:text="≋"
                            android:textColor="@color/accent"
                            android:textSize="29sp" />

                        <TextView
                            android:layout_width="wrap_content"
                            android:layout_height="wrap_content"
                            android:layout_marginTop="2dp"
                            android:text="HYBRID"
                            android:textColor="@color/accent"
                            android:textSize="12sp"
                            android:textStyle="bold" />

                        <TextView
                            android:id="@+id/homeNetworkStatus"
                            android:layout_width="match_parent"
                            android:layout_height="wrap_content"
                            android:layout_marginTop="4dp"
                            android:gravity="center"
                            android:lineSpacingExtra="1dp"
                            android:text="Internet + Mesh\nReady"
                            android:textColor="@color/white_soft"
                            android:textSize="10sp" />
                    </LinearLayout>

                    <View
                        android:layout_width="1dp"
                        android:layout_height="88dp"
                        android:background="@color/border_strong" />

                    <LinearLayout
                        android:layout_width="0dp"
                        android:layout_height="wrap_content"
                        android:layout_weight="1"
                        android:gravity="center"
                        android:orientation="vertical"
                        android:paddingHorizontal="4dp">

                        <TextView
                            android:layout_width="wrap_content"
                            android:layout_height="wrap_content"
                            android:text="◖"
                            android:textColor="@color/accent"
                            android:textSize="29sp" />

                        <TextView
                            android:layout_width="wrap_content"
                            android:layout_height="wrap_content"
                            android:layout_marginTop="2dp"
                            android:text="HELMET"
                            android:textColor="@color/accent"
                            android:textSize="12sp"
                            android:textStyle="bold" />

                        <TextView
                            android:id="@+id/homeAudioStatus"
                            android:layout_width="match_parent"
                            android:layout_height="wrap_content"
                            android:layout_marginTop="4dp"
                            android:gravity="center"
                            android:lineSpacingExtra="1dp"
                            android:text="Bluetooth\nReady"
                            android:textColor="@color/white_soft"
                            android:textSize="10sp" />
                    </LinearLayout>

                    <View
                        android:layout_width="1dp"
                        android:layout_height="88dp"
                        android:background="@color/border_strong" />

                    <LinearLayout
                        android:layout_width="0dp"
                        android:layout_height="wrap_content"
                        android:layout_weight="1"
                        android:gravity="center"
                        android:orientation="vertical"
                        android:paddingHorizontal="4dp">

                        <TextView
                            android:layout_width="wrap_content"
                            android:layout_height="wrap_content"
                            android:text="ϟ"
                            android:textColor="@color/accent"
                            android:textSize="31sp" />

                        <TextView
                            android:layout_width="wrap_content"
                            android:layout_height="wrap_content"
                            android:layout_marginTop="2dp"
                            android:text="SMART POWER"
                            android:textColor="@color/accent"
                            android:textSize="11sp"
                            android:textStyle="bold" />

                        <TextView
                            android:layout_width="match_parent"
                            android:layout_height="wrap_content"
                            android:layout_marginTop="4dp"
                            android:gravity="center"
                            android:lineSpacingExtra="1dp"
                            android:text="Optimized\nExtended Battery"
                            android:textColor="@color/white_soft"
                            android:textSize="10sp" />
                    </LinearLayout>
                </LinearLayout>
            </LinearLayout>

            <TextView
                android:id="@+id/betaExpiryStatus"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="10dp"
                android:gravity="center"
                android:text="BETA ACCESS • 60 DAYS REMAINING"
                android:textColor="@color/accent"
                android:textSize="9sp"
                android:textStyle="bold" />

'''
layout = layout[:status_start] + new_status + layout[footer_start:]
layout = layout.replace(
    'android:layout_marginTop="16dp"\n                android:gravity="center"\n                android:lineSpacingExtra="2dp"\n                android:text="Configure while stopped',
    'android:layout_marginTop="8dp"\n                android:gravity="center"\n                android:lineSpacingExtra="2dp"\n                android:text="Configure while stopped',
    1,
)

# ACTIVE RIDE — preserve functionality while matching the reference scale/hierarchy.
layout = replace_once(
    layout,
    '''        <ImageView
            android:layout_width="224dp"
            android:layout_height="68dp"''',
    '''        <ImageView
            android:layout_width="244dp"
            android:layout_height="72dp"''',
    "active logo size",
)
layout = replace_once(
    layout,
    '''            android:text="RIDE ACTIVE"
            android:textColor="@color/white"
            android:textSize="22sp"''',
    '''            android:text="RIDE ACTIVE"
            android:textColor="@color/white"
            android:textSize="28sp"''',
    "ride active title size",
)
layout = replace_once(
    layout,
    '''            android:text="CONNECTING…"
            android:textColor="@color/accent"
            android:textSize="11sp"''',
    '''            android:text="CONNECTING…"
            android:textColor="@color/accent"
            android:textSize="12sp"''',
    "mesh status size",
)
layout = replace_once(
    layout,
    '''            android:layout_height="76dp"
            android:layout_marginTop="10dp"''',
    '''            android:layout_height="82dp"
            android:layout_marginTop="12dp"''',
    "live panel size",
)
layout = replace_once(
    layout,
    '''                android:layout_width="74dp"
                android:layout_height="52dp"''',
    '''                android:layout_width="68dp"
                android:layout_height="52dp"''',
    "mute button width",
)
layout = replace_once(
    layout,
    '''            android:layout_marginTop="8dp"
            android:layout_weight="1"''',
    '''            android:layout_marginTop="10dp"
            android:layout_weight="1"''',
    "rider grid top spacing",
)

# MAIN ACTIVITY — keep the title fixed and enlarge rider avatars like the approved active screen.
activity = activity.replace(
    '''            internetNode.isConnected() -> {
                val total = internetPeerCount + 1
                binding.networkTile.text = "INTERNET"
                binding.riderCount.text = if (internetPeerCount > 0) "$total RIDERS CONNECTED" else "RIDE ACTIVE"''',
    '''            internetNode.isConnected() -> {
                binding.networkTile.text = "INTERNET"
                binding.riderCount.text = "RIDE ACTIVE"''',
    1,
)
activity = activity.replace(
    '''            directPeerCount > 0 -> {
                val total = directPeerCount + 1
                binding.networkTile.text = "LOCAL MESH"
                binding.riderCount.text = "$total RIDERS NEARBY"''',
    '''            directPeerCount > 0 -> {
                binding.networkTile.text = "LOCAL MESH"
                binding.riderCount.text = "RIDE ACTIVE"''',
    1,
)
activity = activity.replace(
    '''            else -> {
                binding.networkTile.text = "SEARCHING"
                binding.riderCount.text = "RECONNECTING…"''',
    '''            else -> {
                binding.networkTile.text = "SEARCHING"
                binding.riderCount.text = "RIDE ACTIVE"''',
    1,
)

activity = activity.replace(
    '''        binding.homeNetworkStatus.text = when {
            internetNode.isConnected() -> "●  INTERNET VOICE ACTIVE"
            directPeerCount > 0 -> "●  LOCAL MESH ACTIVE"
            else -> "●  READY TO RIDE"
        }''',
    '''        binding.homeNetworkStatus.text = when {
            internetNode.isConnected() -> "Internet Voice\\nActive"
            directPeerCount > 0 -> "Local Mesh\\nActive"
            else -> "Internet + Mesh\\nReady"
        }''',
    1,
)
activity = activity.replace(
    'binding.homeNetworkStatus.text = "●  READY TO RIDE"',
    'binding.homeNetworkStatus.text = "Internet + Mesh\\nReady"',
    1,
)

activity = activity.replace(
    '''        binding.homeAudioStatus.text = when {
            micMuted -> "Microphone muted • incoming voice remains active"
            text.contains("Bluetooth", true) || text.contains("headset", true) -> "Helmet audio • noise reduction ready"
            text.contains("sleep", true) || text.contains("Reconnect", true) || text.contains("Waiting", true) -> "Audio waiting for connection"
            else -> "Phone audio • noise reduction ready"
        }''',
    '''        binding.homeAudioStatus.text = when {
            micMuted -> "Listening Only\\nMic Muted"
            text.contains("Bluetooth", true) || text.contains("headset", true) -> "Connected\\nHelmet Audio"
            text.contains("sleep", true) || text.contains("Reconnect", true) || text.contains("Waiting", true) -> "Audio Link\\nWaiting"
            else -> "Phone Audio\\nReady"
        }''',
    1,
)

activity = activity.replace('height = dp(108)', 'height = dp(136)', 1)
activity = activity.replace('textSize = 22f', 'textSize = 30f', 1)
activity = activity.replace(
    'card.addView(avatar, LinearLayout.LayoutParams(dp(52), dp(52)))',
    'card.addView(avatar, LinearLayout.LayoutParams(dp(72), dp(72)))',
    1,
)
activity = activity.replace('textSize = 10.5f', 'textSize = 14.5f', 1)
activity = activity.replace(
    'LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(21))',
    'LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(26))',
    1,
)
activity = activity.replace('topMargin = dp(3)', 'topMargin = dp(5)', 1)
activity = activity.replace('textSize = 9.5f', 'textSize = 11.5f', 1)
activity = activity.replace(
    'LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(18))',
    'LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(20))',
    1,
)

layout_path.write_text(layout)
activity_path.write_text(activity)

print("Applied approved RideMesh black/cyan reference UI refinements.")
