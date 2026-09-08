from pathlib import Path
import re

# Beta5.6 / vc26 — visible Active Ride UI rebuild matching the approved premium concept.
# Keeps voice, map, riders, billing and subscription behavior unchanged.

p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionCode = 25', 'versionCode = 26')
s = s.replace('versionName = "1.0.0-beta5.5.1-official-logo-lock"', 'versionName = "1.0.0-beta5.6-active-ui-rebuild"')
p.write_text(s)

p = Path('app/src/main/res/layout/activity_main.xml')
s = p.read_text()

start = s.index('    <!-- ACTIVE RIDE -->')
end = s.rindex('\n</FrameLayout>')

active = r'''    <!-- ACTIVE RIDE — Beta5.6 premium rebuild -->
    <LinearLayout
        android:id="@+id/screenActive"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:orientation="vertical"
        android:paddingStart="18dp"
        android:paddingTop="12dp"
        android:paddingEnd="18dp"
        android:paddingBottom="10dp"
        android:visibility="gone">

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="76dp"
            android:gravity="center_vertical"
            android:orientation="horizontal">

            <ImageView
                android:id="@+id/activeRideMeshLogo"
                android:layout_width="252dp"
                android:layout_height="72dp"
                android:contentDescription="RideMesh by Autopilot India"
                android:scaleType="fitStart"
                android:src="@drawable/ridemesh_logo_exact" />

            <Space
                android:layout_width="0dp"
                android:layout_height="1dp"
                android:layout_weight="1" />
        </LinearLayout>

        <View
            android:layout_width="34dp"
            android:layout_height="3dp"
            android:layout_marginTop="8dp"
            android:background="@color/accent" />

        <TextView
            android:id="@+id/riderCount"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginTop="14dp"
            android:fontFamily="sans-serif-condensed"
            android:letterSpacing="0.04"
            android:text="RIDE ACTIVE"
            android:textColor="@color/white"
            android:textSize="34sp"
            android:textStyle="bold" />

        <TextView
            android:id="@+id/meshStatus"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginTop="4dp"
            android:text="●  CONNECTED • LIVE"
            android:textColor="@color/accent"
            android:textSize="13sp"
            android:textStyle="bold" />

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="52dp"
            android:layout_marginTop="16dp"
            android:orientation="horizontal">

            <TextView
                android:id="@+id/networkTile"
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_marginEnd="5dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="READY"
                android:textColor="@color/accent"
                android:textSize="10sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/audioTile"
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_marginHorizontal="5dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="MIC STANDBY"
                android:textColor="@color/white"
                android:textSize="10sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/powerTile"
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_marginStart="5dp"
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
            android:layout_width="match_parent"
            android:layout_height="142dp"
            android:layout_marginTop="16dp"
            android:background="@drawable/live_panel_bg"
            android:gravity="center_vertical"
            android:orientation="horizontal"
            android:paddingStart="18dp"
            android:paddingTop="14dp"
            android:paddingEnd="14dp"
            android:paddingBottom="14dp">

            <LinearLayout
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_weight="1.45"
                android:gravity="center_vertical"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:fontFamily="sans-serif-condensed"
                    android:text="LIVE"
                    android:textColor="@color/accent"
                    android:textSize="25sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="2dp"
                    android:text="HANDS-FREE INTERCOM"
                    android:textColor="@color/white"
                    android:textSize="11sp"
                    android:textStyle="bold" />

                <TextView
                    android:id="@+id/audioStatus"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="7dp"
                    android:maxLines="2"
                    android:text="VOICE-ACTIVATED • NOISE GUARD"
                    android:textColor="@color/muted"
                    android:textSize="9sp" />
            </LinearLayout>

            <View
                android:layout_width="1dp"
                android:layout_height="86dp"
                android:layout_marginHorizontal="10dp"
                android:background="@color/border_strong" />

            <LinearLayout
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_weight="0.95"
                android:gravity="center"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="RIDE CODE"
                    android:textColor="@color/faint"
                    android:textSize="9sp"
                    android:textStyle="bold" />

                <TextView
                    android:id="@+id/activeRideCode"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="4dp"
                    android:text="RM0000"
                    android:textColor="@color/white"
                    android:textSize="21sp"
                    android:textStyle="bold" />
            </LinearLayout>
        </LinearLayout>

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="62dp"
            android:layout_marginTop="10dp"
            android:orientation="horizontal">

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeMute"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="58dp"
                android:layout_marginEnd="6dp"
                android:layout_weight="1"
                android:text="MUTE MIC"
                android:textColor="@color/white"
                android:textSize="12sp"
                android:textStyle="bold"
                app:backgroundTint="@color/panel2"
                app:cornerRadius="16dp"
                app:strokeColor="@color/border_strong"
                app:strokeWidth="1dp" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeStop"
                android:layout_width="0dp"
                android:layout_height="58dp"
                android:layout_marginStart="6dp"
                android:layout_weight="1"
                android:text="END"
                android:textColor="@color/white"
                android:textSize="13sp"
                android:textStyle="bold"
                app:backgroundTint="#D72824"
                app:cornerRadius="16dp" />
        </LinearLayout>

        <GridLayout
            android:id="@+id/riderGrid"
            android:layout_width="match_parent"
            android:layout_height="0dp"
            android:layout_marginTop="12dp"
            android:layout_weight="1"
            android:alignmentMode="alignMargins"
            android:columnCount="1"
            android:gravity="top"
            android:orientation="horizontal"
            android:rowCount="6"
            android:useDefaultMargins="false" />

        <com.google.android.material.button.MaterialButton
            android:id="@+id/activeRiders"
            android:layout_width="1dp"
            android:layout_height="1dp"
            android:visibility="gone"
            android:text="RIDERS" />

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="108dp"
            android:layout_marginTop="8dp"
            android:orientation="horizontal">

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeInvite"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_marginEnd="5dp"
                android:layout_weight="1"
                android:text="INVITE\nINVITE RIDERS"
                android:textColor="@color/white"
                android:textSize="11sp"
                android:textStyle="bold"
                app:backgroundTint="@color/panel2"
                app:cornerRadius="16dp"
                app:strokeColor="@color/border"
                app:strokeWidth="1dp" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeAudio"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_marginHorizontal="5dp"
                android:layout_weight="1"
                android:text="AUDIO\nINTERCOM CONTROLS"
                android:textColor="@color/white"
                android:textSize="11sp"
                android:textStyle="bold"
                app:backgroundTint="@color/panel2"
                app:cornerRadius="16dp"
                app:strokeColor="@color/border"
                app:strokeWidth="1dp" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeStatus"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_marginStart="5dp"
                android:layout_weight="1"
                android:text="STATUS\nRIDE INFORMATION"
                android:textColor="@color/white"
                android:textSize="11sp"
                android:textStyle="bold"
                app:backgroundTint="@color/panel2"
                app:cornerRadius="16dp"
                app:strokeColor="@color/border"
                app:strokeWidth="1dp" />
        </LinearLayout>
    </LinearLayout>
'''

s = s[:start] + active + s[end:]
p.write_text(s)

p = Path('app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt')
s = p.read_text()

pattern = re.compile(r'''    private fun renderRiderGrid\(\) \{.*?\n    private fun qualityGlyphs''', re.S)
replacement = r'''    private fun renderRiderGrid() {
        if (!rideStarted || !::binding.isInitialized) return

        val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val riders = mutableListOf(
            RiderTile(
                key = SELF_TILE_KEY,
                name = me,
                device = deviceLabel(),
                qualityBars = if (internetNode.isConnected() || directPeerCount > 0) 4 else 1,
                path = if (internetNode.isConnected()) "Internet" else if (directPeerCount > 0) "Local" else "Searching",
                self = true,
            )
        )
        if (internetNode.isConnected()) {
            internetNode.remotePeers().forEach { peer ->
                riders += RiderTile(peer.id.toString(), peer.displayName, peer.deviceName, peer.qualityBars, "Internet")
            }
        } else if (meshRunning) {
            meshNode.directPeers().forEach { peer ->
                riders += RiderTile(peer.endpointId, peer.displayName, peer.deviceName, peer.qualityBars, "Local")
            }
        }

        val visible = riders.take(MAX_VISIBLE_RIDER_TILES)
        val grid = binding.riderGrid
        grid.removeAllViews()
        grid.columnCount = 1
        grid.rowCount = visible.size.coerceAtLeast(1)
        visible.forEachIndexed { index, rider ->
            grid.addView(buildRiderTile(rider), GridLayout.LayoutParams().apply {
                rowSpec = GridLayout.spec(index)
                columnSpec = GridLayout.spec(0, 1f)
                width = 0
                height = dp(76)
                setMargins(0, dp(3), 0, dp(3))
            })
        }
    }

    private fun buildRiderTile(rider: RiderTile): View {
        val speaking = (speakingUntilMs[rider.key] ?: 0L) > System.currentTimeMillis()
        val accent = ContextCompat.getColor(this, R.color.accent)
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(8), dp(14), dp(8))
            background = GradientDrawable().apply {
                cornerRadius = dp(18).toFloat()
                setColor(Color.parseColor("#081110"))
                setStroke(dp(if (speaking) 2 else 1), if (speaking) accent else ContextCompat.getColor(this@MainActivity, R.color.border))
            }
        }
        val avatar = TextView(this).apply {
            text = rider.name.trim().firstOrNull()?.uppercaseChar()?.toString() ?: "R"
            gravity = Gravity.CENTER
            textSize = 20f
            setTextColor(Color.WHITE)
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#0A2422"))
                setStroke(dp(1), accent)
            }
        }
        card.addView(avatar, LinearLayout.LayoutParams(dp(50), dp(50)))

        val info = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
        }
        info.addView(TextView(this).apply {
            text = rider.name.ifBlank { "Rider" }
            textSize = 15f
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            setTextColor(if (speaking) accent else Color.WHITE)
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        })
        info.addView(TextView(this).apply {
            text = if (rider.self) "LIVE • YOU" else "LIVE • ${rider.path.uppercase(Locale.ROOT)}"
            textSize = 10.5f
            setTextColor(if (rider.self) accent else ContextCompat.getColor(this@MainActivity, R.color.muted))
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        })
        card.addView(info, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f).apply { marginStart = dp(12) })

        card.addView(TextView(this).apply {
            text = qualityGlyphs(rider.qualityBars)
            textSize = 16f
            setTextColor(qualityColor(rider.qualityBars))
            gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(dp(62), ViewGroup.LayoutParams.MATCH_PARENT))
        return card
    }

    private fun qualityGlyphs'''

s, count = pattern.subn(replacement, s, count=1)
if count != 1:
    raise SystemExit(f'active rider UI replacement count={count}')

p.write_text(s)
