from pathlib import Path

# Keep this script deterministic and idempotent: CI can safely run it more than once.

# Bump the install identity for the refreshed Beta 1.1 package.
p = Path('app/build.gradle.kts')
s = p.read_text()
s = s.replace('versionCode = 11', 'versionCode = 12')
s = s.replace('versionName = "0.4.1-beta1.1"', 'versionName = "0.4.2-beta1.1"')
p.write_text(s)

# Proper launcher resource while keeping the chosen RideMesh artwork as source.
p = Path('app/src/main/AndroidManifest.xml')
s = p.read_text()
s = s.replace('android:icon="@drawable/ridemesh_icon"', 'android:icon="@mipmap/ic_launcher"')
s = s.replace('android:roundIcon="@drawable/ridemesh_icon"', 'android:roundIcon="@mipmap/ic_launcher_round"')
s = s.replace('android:label="Ride Mesh"', 'android:label="RideMesh"')
p.write_text(s)

# Subtle, restrained splash.
p = Path('app/src/main/java/com/bikemesh/ridemesh/SplashActivity.kt')
s = p.read_text()
s = s.replace('widthPixels * 0.68f', 'widthPixels * 0.54f')
s = s.replace('private const val LOGO_REVEAL_MS = 620L', 'private const val LOGO_REVEAL_MS = 540L')
s = s.replace('private const val HOLD_MS = 180L', 'private const val HOLD_MS = 150L')
p.write_text(s)

# Landing page: preserve IDs MainActivity already depends on.
p = Path('app/src/main/res/layout/activity_main.xml')
s = p.read_text()
start_marker = '    <!-- HOME / LANDING -->' if '    <!-- HOME / LANDING -->' in s else '    <!-- HOME -->'
start = s.index(start_marker)
end = s.index('    <!-- SETUP / LOBBY -->')
home = '''    <!-- HOME / LANDING -->
    <ScrollView
        android:id="@+id/screenHome"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:fillViewport="true"
        android:overScrollMode="never">

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:paddingStart="22dp"
            android:paddingTop="18dp"
            android:paddingEnd="22dp"
            android:paddingBottom="24dp">

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="52dp"
                android:gravity="center_vertical"
                android:orientation="horizontal">

                <FrameLayout
                    android:layout_width="46dp"
                    android:layout_height="46dp"
                    android:background="@drawable/icon_plate_bg"
                    android:padding="5dp">
                    <ImageView
                        android:layout_width="match_parent"
                        android:layout_height="match_parent"
                        android:contentDescription="RideMesh"
                        android:scaleType="centerInside"
                        android:src="@drawable/ridemesh_icon" />
                </FrameLayout>

                <LinearLayout
                    android:layout_width="0dp"
                    android:layout_height="wrap_content"
                    android:layout_marginStart="11dp"
                    android:layout_weight="1"
                    android:orientation="vertical">
                    <TextView
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:fontFamily="sans-serif-condensed"
                        android:letterSpacing="0.105"
                        android:text="RIDE MESH"
                        android:textColor="@color/white"
                        android:textSize="19sp"
                        android:textStyle="bold" />
                    <TextView
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:layout_marginTop="1dp"
                        android:text="BY AUTOPILOT INDIA  •  BETA 1.1"
                        android:textColor="@color/accent"
                        android:textSize="8.5sp"
                        android:textStyle="bold" />
                </LinearLayout>

                <com.google.android.material.button.MaterialButton
                    android:id="@+id/openSettings"
                    style="@style/Widget.MaterialComponents.Button.TextButton"
                    android:layout_width="wrap_content"
                    android:layout_height="44dp"
                    android:minWidth="0dp"
                    android:paddingStart="10dp"
                    android:paddingEnd="10dp"
                    android:text="SETTINGS"
                    android:textColor="@color/muted"
                    android:textSize="10sp" />
            </LinearLayout>

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="22dp"
                android:background="@drawable/home_hero_bg"
                android:orientation="vertical"
                android:paddingStart="22dp"
                android:paddingTop="24dp"
                android:paddingEnd="22dp"
                android:paddingBottom="24dp">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="32dp"
                    android:background="@drawable/hero_badge_bg"
                    android:gravity="center"
                    android:paddingStart="12dp"
                    android:paddingEnd="12dp"
                    android:text="HANDS-FREE RIDER INTERCOM"
                    android:textColor="@color/accent"
                    android:textSize="9sp"
                    android:textStyle="bold" />

                <ImageView
                    android:layout_width="match_parent"
                    android:layout_height="88dp"
                    android:layout_marginTop="18dp"
                    android:contentDescription="RideMesh by Autopilot India"
                    android:scaleType="centerInside"
                    android:src="@drawable/ridemesh_logo" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="18dp"
                    android:fontFamily="sans-serif-condensed"
                    android:letterSpacing="0.045"
                    android:text="YOUR GROUP.\nONE CHANNEL."
                    android:textColor="@color/white"
                    android:textSize="31sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="10dp"
                    android:lineSpacingExtra="3dp"
                    android:text="Talk naturally while you ride. RideMesh uses Internet for distance and local mesh as the fallback when coverage disappears."
                    android:textColor="@color/muted"
                    android:textSize="13.5sp" />
            </LinearLayout>

            <com.google.android.material.button.MaterialButton
                android:id="@+id/createRide"
                android:layout_width="match_parent"
                android:layout_height="60dp"
                android:layout_marginTop="22dp"
                android:text="CREATE A RIDE"
                android:textColor="#00201D"
                android:textStyle="bold"
                app:backgroundTint="@color/accent"
                app:cornerRadius="16dp"
                app:icon="@drawable/ic_add_ride"
                app:iconGravity="textStart"
                app:iconPadding="9dp"
                app:iconTint="#00201D" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/joinRide"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="match_parent"
                android:layout_height="58dp"
                android:layout_marginTop="11dp"
                android:text="JOIN A RIDE"
                android:textColor="@color/white"
                android:textStyle="bold"
                app:cornerRadius="16dp"
                app:icon="@drawable/ic_join_ride"
                app:iconGravity="textStart"
                app:iconPadding="9dp"
                app:iconTint="@color/white"
                app:strokeColor="@color/border_strong"
                app:strokeWidth="1dp" />

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="22dp"
                android:background="@drawable/status_card_bg"
                android:orientation="vertical"
                android:padding="18dp">

                <TextView
                    android:id="@+id/homeNetworkStatus"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:text="●  READY TO RIDE"
                    android:textColor="@color/accent"
                    android:textSize="13sp"
                    android:textStyle="bold" />
                <TextView
                    android:id="@+id/homeAudioStatus"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="7dp"
                    android:text="Phone audio ready • helmet optional"
                    android:textColor="@color/white_soft"
                    android:textSize="12sp" />
                <View
                    android:layout_width="match_parent"
                    android:layout_height="1dp"
                    android:layout_marginTop="15dp"
                    android:layout_marginBottom="14dp"
                    android:background="@color/border" />

                <LinearLayout
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:orientation="horizontal">
                    <LinearLayout
                        android:layout_width="0dp"
                        android:layout_height="wrap_content"
                        android:layout_weight="1"
                        android:orientation="vertical">
                        <TextView android:layout_width="wrap_content" android:layout_height="wrap_content" android:text="HYBRID" android:textColor="@color/white" android:textSize="10sp" android:textStyle="bold" />
                        <TextView android:layout_width="wrap_content" android:layout_height="wrap_content" android:layout_marginTop="2dp" android:text="Internet + local" android:textColor="@color/faint_plus" android:textSize="9sp" />
                    </LinearLayout>
                    <LinearLayout
                        android:layout_width="0dp"
                        android:layout_height="wrap_content"
                        android:layout_weight="1"
                        android:orientation="vertical">
                        <TextView android:layout_width="wrap_content" android:layout_height="wrap_content" android:text="HELMET" android:textColor="@color/white" android:textSize="10sp" android:textStyle="bold" />
                        <TextView android:layout_width="wrap_content" android:layout_height="wrap_content" android:layout_marginTop="2dp" android:text="Bluetooth ready" android:textColor="@color/faint_plus" android:textSize="9sp" />
                    </LinearLayout>
                    <LinearLayout
                        android:layout_width="0dp"
                        android:layout_height="wrap_content"
                        android:layout_weight="1"
                        android:orientation="vertical">
                        <TextView android:layout_width="wrap_content" android:layout_height="wrap_content" android:text="SMART POWER" android:textColor="@color/white" android:textSize="10sp" android:textStyle="bold" />
                        <TextView android:layout_width="wrap_content" android:layout_height="wrap_content" android:layout_marginTop="2dp" android:text="Battery aware" android:textColor="@color/faint_plus" android:textSize="9sp" />
                    </LinearLayout>
                </LinearLayout>
            </LinearLayout>

            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="16dp"
                android:gravity="center"
                android:lineSpacingExtra="2dp"
                android:text="Configure while stopped • Once the ride starts, normal voice mode is hands-free."
                android:textColor="@color/faint_plus"
                android:textSize="10.5sp" />
        </LinearLayout>
    </ScrollView>

'''
p.write_text(s[:start] + home + s[end:])

# Supporting colors.
p = Path('app/src/main/res/values/colors.xml')
s = p.read_text()
extras = '''    <color name="icon_bg">#050909</color>\n    <color name="white_soft">#D5DCDA</color>\n    <color name="faint_plus">#687471</color>\n    <color name="border_strong">#30413E</color>\n    <color name="hero_start">#07110F</color>\n    <color name="hero_mid">#0C211E</color>\n    <color name="hero_end">#050706</color>\n'''
if 'name="icon_bg"' not in s:
    s = s.replace('</resources>', extras + '</resources>')
p.write_text(s)

drawables = Path('app/src/main/res/drawable')
drawables.mkdir(parents=True, exist_ok=True)
(drawables / 'home_hero_bg.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>\n<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">\n    <gradient android:angle="315" android:startColor="@color/hero_start" android:centerColor="@color/hero_mid" android:endColor="@color/hero_end" />\n    <corners android:radius="24dp" />\n    <stroke android:width="1dp" android:color="@color/border_strong" />\n</shape>\n''')
(drawables / 'status_card_bg.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>\n<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">\n    <solid android:color="@color/panel" />\n    <corners android:radius="18dp" />\n    <stroke android:width="1dp" android:color="@color/border" />\n</shape>\n''')
(drawables / 'icon_plate_bg.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>\n<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">\n    <solid android:color="@color/panel" />\n    <corners android:radius="13dp" />\n    <stroke android:width="1dp" android:color="@color/border_strong" />\n</shape>\n''')
(drawables / 'hero_badge_bg.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>\n<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">\n    <solid android:color="@color/accent_dim" />\n    <corners android:radius="16dp" />\n    <stroke android:width="1dp" android:color="@color/accent" />\n</shape>\n''')
(drawables / 'ic_add_ride.xml').write_text('''<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="20dp" android:height="20dp" android:viewportWidth="24" android:viewportHeight="24">\n    <path android:fillColor="#00201D" android:pathData="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z" />\n</vector>\n''')
(drawables / 'ic_join_ride.xml').write_text('''<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="20dp" android:height="20dp" android:viewportWidth="24" android:viewportHeight="24">\n    <path android:fillColor="#FFFFFF" android:pathData="M12,4L10.59,5.41L16.17,11H4V13H16.17L10.59,18.59L12,20L20,12Z" />\n</vector>\n''')
(drawables / 'ic_launcher_foreground.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>\n<layer-list xmlns:android="http://schemas.android.com/apk/res/android">\n    <item android:top="16dp" android:bottom="16dp" android:left="16dp" android:right="16dp" android:drawable="@drawable/ridemesh_icon" />\n</layer-list>\n''')

mipmap = Path('app/src/main/res/mipmap-anydpi')
mipmap.mkdir(parents=True, exist_ok=True)
legacy = '''<?xml version="1.0" encoding="utf-8"?>\n<layer-list xmlns:android="http://schemas.android.com/apk/res/android">\n    <item android:drawable="@color/icon_bg" />\n    <item android:top="10dp" android:bottom="10dp" android:left="10dp" android:right="10dp" android:drawable="@drawable/ridemesh_icon" />\n</layer-list>\n'''
(mipmap / 'ic_launcher.xml').write_text(legacy)
(mipmap / 'ic_launcher_round.xml').write_text(legacy)

adaptive = Path('app/src/main/res/mipmap-anydpi-v26')
adaptive.mkdir(parents=True, exist_ok=True)
adaptive_xml = '''<?xml version="1.0" encoding="utf-8"?>\n<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n    <background android:drawable="@color/icon_bg" />\n    <foreground android:drawable="@drawable/ic_launcher_foreground" />\n</adaptive-icon>\n'''
(adaptive / 'ic_launcher.xml').write_text(adaptive_xml)
(adaptive / 'ic_launcher_round.xml').write_text(adaptive_xml)

Path('BETA1_1_UI_REFRESH.md').write_text('''# RideMesh Beta 1.1 — UI refresh\n\nBuild identity: `0.4.2-beta1.1` (`versionCode 12`).\n\n## Presentation\n- Proper adaptive Android launcher icon using the chosen RideMesh icon artwork.\n- App label standardized to `RideMesh`.\n- Existing splash retained but made slightly smaller/faster for a more subtle opening.\n- New landing/home screen with a premium dark RideMesh hero, clear Create/Join actions, readiness status and capability summary.\n- Existing view IDs and ride/session behavior are preserved.\n\n## Safety / usability\n- Landing page states that setup should be done while stopped.\n- The hands-free nature of normal active ride mode remains explicit.\n''')
