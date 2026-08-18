from pathlib import Path
import re

ROOT = Path(".")
def read(path):
    return (ROOT / path).read_text(encoding="utf-8")
def write(path, text):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
def replace_once(text, old, new, label):
    if old in text:
        return text.replace(old, new, 1)
    if new in text:
        return text
    raise SystemExit(f"Patch marker missing: {label}")

# ---- Version ----
p = "app/build.gradle.kts"
t = read(p)
t = t.replace('versionCode = 15', 'versionCode = 16')
t = t.replace('versionName = "0.4.5-beta1.1"', 'versionName = "0.4.6-beta1.2"')
write(p, t)

# ---- Manifest: exact supplied artwork ----
p = "app/src/main/AndroidManifest.xml"
t = read(p)
t = t.replace('android:icon="@drawable/ridemesh_app_icon"', 'android:icon="@drawable/ridemesh_icon_exact"')
t = t.replace('android:roundIcon="@drawable/ridemesh_app_icon"', 'android:roundIcon="@drawable/ridemesh_icon_exact"')
t = t.replace('android:logo="@drawable/ridemesh_brand_mark"', 'android:logo="@drawable/ridemesh_logo_exact"')
write(p, t)

# ---- Splash: exact full logo, no recreated text ----
p = "app/src/main/java/com/bikemesh/ridemesh/SplashActivity.kt"
t = read(p)
start = t.index("class SplashActivity")
prefix = t[:start]
new_class = r'''class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = android.widget.FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
        }
        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_logo_exact)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            alpha = 0f
            scaleX = 0.97f
            scaleY = 0.97f
        }

        val width = (resources.displayMetrics.widthPixels * 0.76f).toInt()
        val height = (width * 189f / 342f).toInt()
        root.addView(
            logo,
            android.widget.FrameLayout.LayoutParams(width, height, Gravity.CENTER)
        )
        setContentView(root)

        logo.animate()
            .alpha(1f)
            .scaleX(1f)
            .scaleY(1f)
            .setDuration(LOGO_REVEAL_MS)
            .withEndAction {
                logo.postDelayed({
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                }, HOLD_MS)
            }
            .start()
    }

    companion object {
        private const val LOGO_REVEAL_MS = 440L
        private const val HOLD_MS = 120L
    }
}
'''
write(p, prefix + new_class)

# ---- Compact rectangle + rider grid ----
p = "app/src/main/res/layout/activity_main.xml"
t = read(p)

old_home = '''                <ImageView
                    android:layout_width="62dp"
                    android:layout_height="62dp"
                    android:contentDescription="RideMesh logo"
                    android:scaleType="centerInside"
                    android:src="@drawable/ridemesh_brand_mark" />

                <LinearLayout
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_marginStart="9dp"
                    android:layout_weight="1"
                    android:orientation="vertical">
                    <TextView
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:fontFamily="sans-serif-condensed"
                        android:letterSpacing="0.105"
                        android:text="RIDE MESH"
                        android:textColor="@color/white"
                        android:textSize="20sp"
                        android:textStyle="bold" />
                    <TextView
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:layout_marginTop="2dp"
                        android:text="BY AUTOPILOT INDIA  •  BETA 1.1"
                        android:textColor="@color/accent"
                        android:textSize="8.5sp"
                        android:textStyle="bold" />
                </LinearLayout>
'''
new_home = '''                <ImageView
                    android:layout_width="154dp"
                    android:layout_height="62dp"
                    android:layout_weight="1"
                    android:contentDescription="RideMesh by Autopilot India"
                    android:scaleType="fitStart"
                    android:src="@drawable/ridemesh_logo_exact" />
'''
t = replace_once(t, old_home, new_home, "home exact logo")

active = r'''    <!-- ACTIVE RIDE -->
    <LinearLayout
        android:id="@+id/screenActive"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:orientation="vertical"
        android:paddingStart="18dp"
        android:paddingTop="14dp"
        android:paddingEnd="18dp"
        android:paddingBottom="14dp"
        android:visibility="gone">

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="54dp"
            android:gravity="center_vertical"
            android:orientation="horizontal">

            <ImageView
                android:layout_width="142dp"
                android:layout_height="52dp"
                android:contentDescription="RideMesh by Autopilot India"
                android:scaleType="fitStart"
                android:src="@drawable/ridemesh_logo_exact" />

            <TextView
                android:id="@+id/activeRideCode"
                android:layout_width="0dp"
                android:layout_height="wrap_content"
                android:layout_marginStart="8dp"
                android:layout_weight="1"
                android:gravity="center_vertical"
                android:text="RM0000"
                android:textColor="@color/muted"
                android:textSize="10sp"
                android:textStyle="bold" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeStop"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="72dp"
                android:layout_height="40dp"
                android:text="END"
                android:textColor="@color/white"
                android:textSize="10sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/border" />
        </LinearLayout>

        <TextView
            android:id="@+id/riderCount"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginTop="10dp"
            android:fontFamily="sans-serif-condensed"
            android:gravity="center"
            android:text="RIDE ACTIVE"
            android:textColor="@color/white"
            android:textSize="22sp"
            android:textStyle="bold" />

        <TextView
            android:id="@+id/meshStatus"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginTop="5dp"
            android:gravity="center"
            android:text="CONNECTING…"
            android:textColor="@color/accent"
            android:textSize="11sp"
            android:textStyle="bold" />

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="46dp"
            android:layout_marginTop="11dp"
            android:gravity="center"
            android:orientation="horizontal">

            <TextView
                android:id="@+id/networkTile"
                android:layout_width="0dp"
                android:layout_height="38dp"
                android:layout_marginEnd="4dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="CONNECTING"
                android:textColor="@color/accent"
                android:textSize="10sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/audioTile"
                android:layout_width="0dp"
                android:layout_height="38dp"
                android:layout_marginHorizontal="4dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="VOICE CLEAN"
                android:textColor="@color/white"
                android:textSize="10sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/powerTile"
                android:layout_width="0dp"
                android:layout_height="38dp"
                android:layout_marginStart="4dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="SMART POWER"
                android:textColor="@color/green"
                android:textSize="10sp"
                android:textStyle="bold" />
        </LinearLayout>

        <LinearLayout
            android:id="@+id/handsFreeIndicator"
            android:layout_width="218dp"
            android:layout_height="66dp"
            android:layout_gravity="center_horizontal"
            android:layout_marginTop="10dp"
            android:background="@drawable/live_panel_bg"
            android:gravity="center"
            android:orientation="vertical"
            android:paddingHorizontal="14dp"
            android:paddingVertical="6dp">

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:fontFamily="sans-serif-condensed"
                android:letterSpacing="0.07"
                android:text="LIVE"
                android:textColor="@color/accent"
                android:textSize="18sp"
                android:textStyle="bold" />

            <TextView
                android:layout_width="wrap_content"
                android:layout_height="wrap_content"
                android:layout_marginTop="1dp"
                android:text="HANDS-FREE INTERCOM"
                android:textColor="@color/white"
                android:textSize="9sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/audioStatus"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="2dp"
                android:ellipsize="end"
                android:gravity="center"
                android:maxLines="1"
                android:text="VOICE-ACTIVATED • NOISE GUARD"
                android:textColor="@color/muted"
                android:textSize="7.5sp" />
        </LinearLayout>

        <GridLayout
            android:id="@+id/riderGrid"
            android:layout_width="match_parent"
            android:layout_height="0dp"
            android:layout_marginTop="8dp"
            android:layout_weight="1"
            android:alignmentMode="alignMargins"
            android:columnCount="3"
            android:gravity="center"
            android:orientation="horizontal"
            android:rowCount="2"
            android:useDefaultMargins="false" />

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="62dp"
            android:orientation="horizontal">

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeRiders"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginEnd="4dp"
                android:layout_weight="1"
                android:text="RIDERS"
                android:textColor="@color/white"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/border" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeInvite"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginHorizontal="4dp"
                android:layout_weight="1"
                android:text="INVITE"
                android:textColor="@color/accent"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/accent" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeAudio"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginHorizontal="4dp"
                android:layout_weight="1"
                android:text="AUDIO"
                android:textColor="@color/white"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/border" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeStatus"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginStart="4dp"
                android:layout_weight="1"
                android:text="STATUS"
                android:textColor="@color/white"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/border" />
        </LinearLayout>
    </LinearLayout>
'''
t2, n = re.subn(r'    <!-- ACTIVE RIDE -->.*?\n    </LinearLayout>\n</FrameLayout>\s*$', active + '\n</FrameLayout>\n', t, count=1, flags=re.S)
if n != 1:
    if 'android:id="@+id/riderGrid"' not in t:
        raise SystemExit("Could not replace active ride section")
    t2 = t
write(p, t2)

write("app/src/main/res/drawable/live_panel_bg.xml", '''<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <solid android:color="#101918" />
    <stroke android:width="1dp" android:color="#00E6E6" />
    <corners android:radius="16dp" />
</shape>
''')

# ---- MainActivity: rider cards, speaking glow, friendly names ----
p = "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt"
t = read(p)
if "import android.graphics.Typeface" not in t:
    t = t.replace("import android.graphics.Color\n", "import android.graphics.Color\nimport android.graphics.Typeface\nimport android.graphics.drawable.GradientDrawable\n")
if "import android.view.Gravity" not in t:
    t = t.replace("import android.view.View\n", "import android.view.Gravity\nimport android.view.View\nimport android.view.ViewGroup\n")
if "import android.widget.GridLayout" not in t:
    t = t.replace("import android.widget.ImageView\n", "import android.widget.GridLayout\nimport android.widget.ImageView\nimport android.widget.LinearLayout\nimport android.widget.TextView\n")
if "import java.util.concurrent.ConcurrentHashMap" not in t:
    t = t.replace("import java.util.Locale\n", "import java.util.Locale\nimport java.util.concurrent.ConcurrentHashMap\n")

marker = '    private val mainHandler = Handler(Looper.getMainLooper())\n'
if "speakingUntilMs" not in t:
    t = t.replace(marker, marker + '    private val speakingUntilMs = ConcurrentHashMap<String, Long>()\n')

enum_marker = '    private enum class Screen { HOME, SETUP, ACTIVE }\n'
if "data class RiderTile" not in t:
    t = t.replace(enum_marker, enum_marker + '''
    private data class RiderTile(
        val key: String,
        val name: String,
        val device: String,
        val qualityBars: Int,
        val path: String,
        val self: Boolean = false,
    )
''')

t = t.replace('        binding.activeRiderNames.text = ""\n', '        binding.riderGrid.removeAllViews()\n        speakingUntilMs.clear()\n')
t = t.replace('        updateRiderRosterPreview()\n', '        renderRiderGrid()\n')

t = t.replace('binding.riderName.setText(prefs.getString("rider", Build.MODEL.take(18)))',
'''val savedRider = prefs.getString("rider", "").orEmpty()
        binding.riderName.setText(
            savedRider.takeIf { it.isNotBlank() && !it.equals(Build.MODEL, ignoreCase = true) } ?: "Rider"
        )''')
t = t.replace('val rider = binding.riderName.text?.toString().orEmpty().ifBlank { Build.MODEL.take(18) }',
              'val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }')

t = t.replace('''    override fun onAudioPacket(sourceId: String, audio: ByteArray) {
        if (rideStarted) audioEngine.playIncoming(sourceId, audio)
    }
''', '''    override fun onAudioPacket(sourceId: String, audio: ByteArray) {
        if (!rideStarted) return
        val tileKey = meshNode.endpointIdForSource(sourceId) ?: sourceId
        markRiderSpeaking(tileKey)
        audioEngine.playIncoming(sourceId, audio)
    }
''')
t = t.replace('''    override fun onInternetAudio(sourceId: String, audio: ByteArray) {
        if (rideStarted) audioEngine.playIncoming(sourceId, audio)
    }
''', '''    override fun onInternetAudio(sourceId: String, audio: ByteArray) {
        if (!rideStarted) return
        markRiderSpeaking(sourceId)
        audioEngine.playIncoming(sourceId, audio)
    }
''')

roster_pattern = re.compile(r'    private fun updateRiderRosterPreview\(\) \{.*?\n    \}\n\n    private fun applyPowerUi', re.S)
new_roster = r'''    private fun markRiderSpeaking(key: String) {
        val expires = System.currentTimeMillis() + SPEAKING_HOLD_MS
        speakingUntilMs[key] = expires
        runOnUiThread {
            renderRiderGrid()
            mainHandler.postDelayed({
                val current = speakingUntilMs[key] ?: return@postDelayed
                if (System.currentTimeMillis() >= current) {
                    speakingUntilMs.remove(key, current)
                    renderRiderGrid()
                }
            }, SPEAKING_HOLD_MS + 40L)
        }
    }

    private fun renderRiderGrid() {
        if (!rideStarted || !::binding.isInitialized) return

        val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val meDevice = deviceLabel()
        val riders = mutableListOf(
            RiderTile(
                key = SELF_TILE_KEY,
                name = me,
                device = meDevice,
                qualityBars = if (internetNode.isConnected() || directPeerCount > 0) 4 else 1,
                path = if (internetNode.isConnected()) "Internet" else if (directPeerCount > 0) "Local" else "Searching",
                self = true,
            )
        )

        if (internetNode.isConnected()) {
            internetNode.remotePeers().forEach { peer ->
                riders += RiderTile(
                    key = peer.id.toString(),
                    name = peer.displayName,
                    device = peer.deviceName,
                    qualityBars = peer.qualityBars,
                    path = "Internet",
                )
            }
        } else if (meshRunning) {
            meshNode.directPeers().forEach { peer ->
                riders += RiderTile(
                    key = peer.endpointId,
                    name = peer.displayName,
                    device = peer.deviceName,
                    qualityBars = peer.qualityBars,
                    path = "Local",
                )
            }
        }

        val visible = riders.take(MAX_VISIBLE_RIDER_TILES)
        val grid = binding.riderGrid
        grid.removeAllViews()
        grid.columnCount = 3
        grid.rowCount = if (visible.size <= 3) 1 else 2

        val positions = riderPositions(visible.size)
        visible.forEachIndexed { index, rider ->
            val (row, col) = positions[index]
            grid.addView(buildRiderTile(rider), GridLayout.LayoutParams().apply {
                rowSpec = GridLayout.spec(row)
                columnSpec = GridLayout.spec(col, 1f)
                width = 0
                height = dp(108)
                setMargins(dp(3), dp(3), dp(3), dp(3))
            })
        }
    }

    private fun buildRiderTile(rider: RiderTile): View {
        val speaking = (speakingUntilMs[rider.key] ?: 0L) > System.currentTimeMillis()
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(3), dp(3), dp(3), dp(2))
        }

        val avatar = TextView(this).apply {
            text = rider.name.trim().firstOrNull()?.uppercaseChar()?.toString() ?: "R"
            gravity = Gravity.CENTER
            textSize = 22f
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#101918"))
                setStroke(
                    dp(if (speaking) 3 else 1),
                    if (speaking) ContextCompat.getColor(this@MainActivity, R.color.accent)
                    else ContextCompat.getColor(this@MainActivity, R.color.border)
                )
            }
        }
        card.addView(avatar, LinearLayout.LayoutParams(dp(52), dp(52)))

        val name = TextView(this).apply {
            text = rider.name.ifBlank { "Rider" }
            gravity = Gravity.CENTER
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            textSize = 10.5f
            setTextColor(
                ContextCompat.getColor(
                    this@MainActivity,
                    if (speaking) R.color.accent else R.color.white
                )
            )
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        }
        card.addView(name, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(21)).apply {
            topMargin = dp(3)
        })

        val quality = TextView(this).apply {
            text = if (rider.self) "YOU  ${qualityGlyphs(rider.qualityBars)}" else qualityGlyphs(rider.qualityBars)
            gravity = Gravity.CENTER
            textSize = 9.5f
            setTextColor(qualityColor(rider.qualityBars))
        }
        card.addView(quality, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(18)))
        return card
    }

    private fun riderPositions(count: Int): List<Pair<Int, Int>> = when (count.coerceIn(1, 6)) {
        1 -> listOf(0 to 1)
        2 -> listOf(0 to 0, 0 to 2)
        3 -> listOf(0 to 0, 0 to 1, 0 to 2)
        4 -> listOf(0 to 0, 0 to 2, 1 to 0, 1 to 2)
        5 -> listOf(0 to 0, 0 to 1, 0 to 2, 1 to 0, 1 to 2)
        else -> listOf(0 to 0, 0 to 1, 0 to 2, 1 to 0, 1 to 1, 1 to 2)
    }

    private fun qualityGlyphs(bars: Int): String {
        val clamped = bars.coerceIn(1, 4)
        val levels = arrayOf("▂", "▄", "▆", "█")
        return levels.mapIndexed { index, glyph -> if (index < clamped) glyph else "·" }.joinToString("")
    }

    private fun qualityColor(bars: Int): Int = when (bars.coerceIn(1, 4)) {
        1 -> Color.parseColor("#FF6B6B")
        2 -> ContextCompat.getColor(this, R.color.amber)
        else -> ContextCompat.getColor(this, R.color.accent)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun applyPowerUi'''
t, n = roster_pattern.subn(new_roster, t, count=1)
if n != 1 and "private fun renderRiderGrid()" not in t:
    raise SystemExit("Could not replace rider roster preview")

t = t.replace('val me = binding.riderName.text?.toString().orEmpty().ifBlank { Build.MODEL.take(18) }',
              'val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }')

const_marker = '    companion object {\n'
if "SPEAKING_HOLD_MS" not in t:
    t = t.replace(const_marker, const_marker + '''        private const val SELF_TILE_KEY = "self"
        private const val MAX_VISIBLE_RIDER_TILES = 6
        private const val SPEAKING_HOLD_MS = 560L
''', 1)
write(p, t)

# ---- Mesh source -> tile best-effort mapping ----
p = "app/src/main/java/com/bikemesh/ridemesh/mesh/MeshNode.kt"
t = read(p)
if "originEndpoints" not in t:
    t = t.replace('    private val endpointNames = ConcurrentHashMap<String, String>()\n',
                  '    private val endpointNames = ConcurrentHashMap<String, String>()\n    private val originEndpoints = ConcurrentHashMap<UUID, String>()\n')
    t = t.replace('                if (packet.origin != nodeId && packet.audio.isNotEmpty()) {\n',
                  '                if (packet.origin != nodeId) originEndpoints[packet.origin] = endpointId\n\n                if (packet.origin != nodeId && packet.audio.isNotEmpty()) {\n')
    t = t.replace('            connected.remove(endpointId)\n            requested.remove(endpointId)\n',
                  '            connected.remove(endpointId)\n            requested.remove(endpointId)\n            originEndpoints.entries.removeIf { it.value == endpointId }\n', 1)
    t = t.replace('        endpointNames.clear()\n        listener.onDirectPeerCount(0)\n',
                  '        endpointNames.clear()\n        originEndpoints.clear()\n        listener.onDirectPeerCount(0)\n')
    t = t.replace('    fun directPeers(): List<RiderPeer> = connected.mapNotNull { endpointId ->\n',
                  '''    fun endpointIdForSource(sourceId: String): String? = runCatching {
        originEndpoints[UUID.fromString(sourceId)]
    }.getOrNull()

    fun directPeers(): List<RiderPeer> = connected.mapNotNull { endpointId ->
''')
    t = t.replace('        val deviceName: String,\n    ) {',
                  '        val deviceName: String,\n        val qualityBars: Int = 4,\n    ) {', 1)
write(p, t)

# ---- Internet voice quality estimator for rider bars ----
p = "app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt"
t = read(p)
if "linkStats" not in t:
    t = t.replace('    private val peers = ConcurrentHashMap<UUID, RiderPeer>()\n',
                  '    private val peers = ConcurrentHashMap<UUID, RiderPeer>()\n    private val linkStats = ConcurrentHashMap<UUID, LinkStats>()\n')
    t = t.replace('                if (packet.origin == nodeId) return\n                touchPeer(packet.origin)\n',
                  '                if (packet.origin == nodeId) return\n                updateLinkStats(packet)\n                touchPeer(packet.origin)\n')
    t = t.replace('RiderPeer(id = id, riderName = "", deviceName = "", lastSeenMs = now)',
                  'RiderPeer(id = id, riderName = "", deviceName = "", lastSeenMs = now, qualityBars = qualityBarsFor(id))')
    t = t.replace('current.copy(lastSeenMs = now)',
                  'current.copy(lastSeenMs = now, qualityBars = qualityBarsFor(id))')
    t = t.replace('peers[id] = RiderPeer(id, resolvedRider, resolvedDevice, now)',
                  'peers[id] = RiderPeer(id, resolvedRider, resolvedDevice, now, previous?.qualityBars ?: qualityBarsFor(id))')
    t = t.replace('        peers.clear()\n        notifyPeerCount(force = true)\n',
                  '        peers.clear()\n        linkStats.clear()\n        notifyPeerCount(force = true)\n')
    insert_before = '    private fun prunePeers(now: Long) {\n'
    quality_code = r'''    private data class LinkStats(
        var lastArrivalMs: Long = 0L,
        var lastSequence: Int? = null,
        var jitterEwmaMs: Double = 0.0,
        var lossEwma: Double = 0.0,
    )

    private fun updateLinkStats(packet: InternetPacket) {
        val now = System.currentTimeMillis()
        val stats = linkStats.computeIfAbsent(packet.origin) { LinkStats() }

        if (stats.lastArrivalMs > 0L) {
            val interval = now - stats.lastArrivalMs
            if (interval in 5L..400L) {
                val deviation = kotlin.math.abs(interval.toDouble() - 20.0)
                stats.jitterEwmaMs = (stats.jitterEwmaMs * 0.85) + (deviation * 0.15)
            }
        }

        val previousSequence = stats.lastSequence
        if (previousSequence != null) {
            val delta = packet.sequence.toLong() - previousSequence.toLong()
            if (delta in 1L..1000L) {
                val missing = (delta - 1L).coerceAtLeast(0L)
                val sampleLoss = missing.toDouble() / delta.toDouble()
                stats.lossEwma = (stats.lossEwma * 0.90) + (sampleLoss * 0.10)
            }
        }

        stats.lastArrivalMs = now
        stats.lastSequence = packet.sequence
        val quality = qualityBars(stats)
        peers.computeIfPresent(packet.origin) { _, current -> current.copy(qualityBars = quality) }
    }

    private fun qualityBarsFor(id: UUID): Int = linkStats[id]?.let(::qualityBars) ?: 4

    private fun qualityBars(stats: LinkStats): Int = when {
        stats.lossEwma >= 0.15 || stats.jitterEwmaMs >= 75.0 -> 1
        stats.lossEwma >= 0.08 || stats.jitterEwmaMs >= 45.0 -> 2
        stats.lossEwma >= 0.03 || stats.jitterEwmaMs >= 22.0 -> 3
        else -> 4
    }

'''
    t = t.replace(insert_before, quality_code + insert_before)
    t = t.replace('        val lastSeenMs: Long,\n    ) {',
                  '        val lastSeenMs: Long,\n        val qualityBars: Int = 4,\n    ) {', 1)
write(p, t)

# ---- Audio: focus handling, faster buffers, audio-priority threads, tuned VAD ----
p = "app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt"
t = read(p)
if "import android.media.AudioFocusRequest" not in t:
    t = t.replace("import android.media.AudioFormat\n", "import android.media.AudioFormat\nimport android.media.AudioFocusRequest\n")
if "import android.os.Process" not in t:
    t = t.replace("import android.os.Build\n", "import android.os.Build\nimport android.os.Process\n")

if "transmitDesired" not in t:
    t = t.replace('    private val capturing = AtomicBoolean(false)\n    private val playbackRunning = AtomicBoolean(true)\n',
'''    private val capturing = AtomicBoolean(false)
    private val playbackRunning = AtomicBoolean(true)
    private val transmitDesired = AtomicBoolean(false)
    private val focusPaused = AtomicBoolean(false)
    private val focusHeld = AtomicBoolean(false)
''')
    focus_insert = r'''    private val voiceAttributes = AudioAttributes.Builder()
        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
        .build()

    private val audioFocusListener = AudioManager.OnAudioFocusChangeListener { change ->
        when (change) {
            AudioManager.AUDIOFOCUS_GAIN -> resumeAfterAudioFocus()
            AudioManager.AUDIOFOCUS_LOSS,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> pauseForAudioFocus()
        }
    }

    private val audioFocusRequest: AudioFocusRequest by lazy {
        AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(voiceAttributes)
            .setAcceptsDelayedFocusGain(true)
            .setWillPauseWhenDucked(true)
            .setOnAudioFocusChangeListener(audioFocusListener)
            .build()
    }

    private fun ensureAudioFocus(): Boolean {
        if (focusHeld.get() && !focusPaused.get()) return true
        return when (audioManager.requestAudioFocus(audioFocusRequest)) {
            AudioManager.AUDIOFOCUS_REQUEST_GRANTED -> {
                focusHeld.set(true)
                focusPaused.set(false)
                true
            }
            AudioManager.AUDIOFOCUS_REQUEST_DELAYED -> {
                focusHeld.set(true)
                focusPaused.set(true)
                onStatus("PAUSED FOR PHONE CALL • AUTO RESUME")
                false
            }
            else -> {
                focusHeld.set(false)
                focusPaused.set(true)
                onStatus("AUDIO BUSY • WAITING TO RESUME")
                false
            }
        }
    }

    private fun pauseForAudioFocus() {
        focusPaused.set(true)
        capturing.set(false)
        clearRemoteAudio()
        audioTrack?.let {
            try { it.pause() } catch (_: Throwable) {}
            try { it.flush() } catch (_: Throwable) {}
        }
        onStatus("PAUSED FOR PHONE CALL • AUTO RESUME")
    }

    private fun resumeAfterAudioFocus() {
        focusHeld.set(true)
        focusPaused.set(false)
        selectCommunicationDevice()
        audioTrack?.let {
            try { it.play() } catch (_: Throwable) {}
        }
        onStatus("HANDS-FREE • AUDIO RESUMED")
        if (transmitDesired.get()) startRecorder()
    }

    private fun clearRemoteAudio() {
        sourceQueues.values.forEach { queue -> synchronized(queue) { queue.clear() } }
        sourcePrimed.clear()
        sourceLastSeenMs.clear()
    }

'''
    t = t.replace('    fun setRoute(newRoute: AudioRoute) {\n', focus_insert + '    fun setRoute(newRoute: AudioRoute) {\n')

    t = t.replace('''    @SuppressLint("MissingPermission")
    fun startTransmit() {
        if (!capturing.compareAndSet(false, true)) return
''', '''    @SuppressLint("MissingPermission")
    fun startTransmit() {
        transmitDesired.set(true)
        if (!ensureAudioFocus() || focusPaused.get()) return
        startRecorder()
    }

    @SuppressLint("MissingPermission")
    private fun startRecorder() {
        if (!capturing.compareAndSet(false, true)) return
''')
    t = t.replace('            val recordBuffer = max(min, FRAME_BYTES * 4)\n',
                  '            val recordBuffer = max(min, FRAME_BYTES * 2)\n')
    t = t.replace('''            Thread({
                val frame = ByteArray(FRAME_BYTES)
''', '''            Thread({
                Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
                val frame = ByteArray(FRAME_BYTES)
''')
    t = t.replace('                    if (audioRecord === activeRecorder) audioRecord = null\n                    selectCommunicationDevice()\n',
                  '                    if (audioRecord === activeRecorder) audioRecord = null\n                    if (!focusPaused.get()) selectCommunicationDevice()\n')
    t = t.replace('''    fun stopTransmit() {
        capturing.set(false)
    }
''', '''    fun stopTransmit() {
        transmitDesired.set(false)
        capturing.set(false)
    }
''')
    t = t.replace('        if (audio.isEmpty() || !playbackRunning.get()) return\n',
                  '        if (audio.isEmpty() || !playbackRunning.get() || focusPaused.get()) return\n', 1)
    t = t.replace('''    private fun playbackLoop() {
        while (playbackRunning.get()) {
''', '''    private fun playbackLoop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
        while (playbackRunning.get()) {
            if (focusPaused.get()) {
                try { Thread.sleep(PLAYBACK_IDLE_SLEEP_MS) } catch (_: InterruptedException) { break }
                continue
            }
''')
    t = t.replace('        sourceLastSeenMs.clear()\n        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {',
                  '''        sourceLastSeenMs.clear()
        if (focusHeld.getAndSet(false)) {
            try { audioManager.abandonAudioFocusRequest(audioFocusRequest) } catch (_: Throwable) {}
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {''')
    t = t.replace('''                .setBufferSizeInBytes(max(min, FRAME_BYTES * 3))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()
''', '''                .setBufferSizeInBytes(max(min, FRAME_BYTES * 2))
                .setTransferMode(AudioTrack.MODE_STREAM)
                .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
                .build()
''')
    t = t.replace('private const val VAD_PREROLL_FRAMES = 3', 'private const val VAD_PREROLL_FRAMES = 2')
    t = t.replace('private const val VAD_HANGOVER_FRAMES = 8 // 160 ms; shorter to reduce echo tails',
                  'private const val VAD_HANGOVER_FRAMES = 5 // 100 ms: fast close without clipping word endings')
    t = t.replace('private const val VAD_MIN_RMS = 520.0', 'private const val VAD_MIN_RMS = 480.0')
    t = t.replace('private const val VAD_NOISE_MULTIPLIER = 2.2', 'private const val VAD_NOISE_MULTIPLIER = 2.05')
write(p, t)

print("Beta 1.2 patch applied")
