from pathlib import Path

p = Path('app/src/main/res/layout/activity_main.xml')
s = p.read_text()

def replace_once(text, old, new):
    if old not in text:
        raise SystemExit(f'Missing expected block: {old[:120]!r}')
    return text.replace(old, new, 1)

def replace_section(text, start, end, replacement):
    a = text.find(start)
    if a < 0:
        raise SystemExit(f'Missing section start: {start[:120]!r}')
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f'Missing section end: {end[:120]!r}')
    return text[:a] + replacement + text[b:]

# Home header: approved horizontal RideMesh logo treatment and settings alignment.
s = replace_once(s, 'android:layout_height="66dp"\n                android:gravity="center_vertical"', 'android:layout_height="78dp"\n                android:gravity="center_vertical"')
s = replace_once(s, 'android:layout_width="154dp"\n                    android:layout_height="62dp"', 'android:layout_width="218dp"\n                    android:layout_height="76dp"')
s = replace_once(s, 'android:minWidth="0dp"\n                    android:paddingStart="10dp"', 'android:minWidth="0dp"\n                    android:layout_marginTop="6dp"\n                    android:paddingStart="8dp"')
s = replace_once(s, 'android:paddingEnd="10dp"\n                    android:text="SETTINGS"', 'android:paddingEnd="8dp"\n                    android:text="SETTINGS"')

# Approved side-by-side home actions.
start_actions = '            <com.google.android.material.button.MaterialButton\n                android:id="@+id/createRide"'
end_actions = '            <LinearLayout\n                android:layout_width="match_parent"\n                android:layout_height="wrap_content"\n                android:layout_marginTop="22dp"\n                android:background="@drawable/status_card_bg"'
new_actions = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="60dp"
                android:layout_marginTop="22dp"
                android:orientation="horizontal">

                <com.google.android.material.button.MaterialButton
                    android:id="@+id/createRide"
                    android:layout_width="0dp"
                    android:layout_height="58dp"
                    android:layout_marginEnd="6dp"
                    android:layout_weight="1"
                    android:text="CREATE A RIDE"
                    android:textColor="#00201D"
                    android:textSize="11sp"
                    android:textStyle="bold"
                    app:backgroundTint="@color/accent"
                    app:cornerRadius="16dp"
                    app:icon="@drawable/ic_add_ride"
                    app:iconGravity="textStart"
                    app:iconPadding="6dp"
                    app:iconTint="#00201D" />

                <com.google.android.material.button.MaterialButton
                    android:id="@+id/joinRide"
                    style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                    android:layout_width="0dp"
                    android:layout_height="58dp"
                    android:layout_marginStart="6dp"
                    android:layout_weight="1"
                    android:text="JOIN A RIDE"
                    android:textColor="@color/white"
                    android:textSize="11sp"
                    android:textStyle="bold"
                    app:cornerRadius="16dp"
                    app:icon="@drawable/ic_join_ride"
                    app:iconGravity="textStart"
                    app:iconPadding="6dp"
                    app:iconTint="@color/white"
                    app:strokeColor="@color/accent"
                    app:strokeWidth="1dp" />
            </LinearLayout>

'''
s = replace_section(s, start_actions, end_actions, new_actions)

# Active header: full horizontal RideMesh branding only. Ride code + END move into LIVE panel.
active_header_start = '''        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="54dp"
            android:gravity="center_vertical"
            android:orientation="horizontal">'''
active_header_end = '''        <TextView
            android:id="@+id/riderCount"'''
active_header = '''        <ImageView
            android:layout_width="224dp"
            android:layout_height="68dp"
            android:contentDescription="RideMesh by Autopilot India"
            android:scaleType="fitStart"
            android:src="@drawable/ridemesh_logo_exact" />

'''
s = replace_section(s, active_header_start, active_header_end, active_header)

# Compact LIVE rectangle with ride code and END at the same level, no second-group controls.
live_start = '''        <LinearLayout
            android:id="@+id/handsFreeIndicator"'''
live_end = '''        <GridLayout
            android:id="@+id/riderGrid"'''
live_panel = '''        <LinearLayout
            android:id="@+id/handsFreeIndicator"
            android:layout_width="match_parent"
            android:layout_height="76dp"
            android:layout_marginTop="10dp"
            android:background="@drawable/live_panel_bg"
            android:gravity="center_vertical"
            android:orientation="horizontal"
            android:paddingStart="16dp"
            android:paddingEnd="8dp">

            <LinearLayout
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_weight="1"
                android:gravity="center_vertical"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:fontFamily="sans-serif-condensed"
                    android:letterSpacing="0.07"
                    android:text="LIVE"
                    android:textColor="@color/accent"
                    android:textSize="19sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="HANDS-FREE INTERCOM"
                    android:textColor="@color/white"
                    android:textSize="9.5sp"
                    android:textStyle="bold" />

                <TextView
                    android:id="@+id/audioStatus"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="2dp"
                    android:ellipsize="end"
                    android:maxLines="1"
                    android:text="VOICE-ACTIVATED • NOISE GUARD"
                    android:textColor="@color/muted"
                    android:textSize="7.5sp" />
            </LinearLayout>

            <View
                android:layout_width="1dp"
                android:layout_height="46dp"
                android:layout_marginHorizontal="8dp"
                android:background="@color/border_strong" />

            <TextView
                android:id="@+id/activeRideCode"
                android:layout_width="78dp"
                android:layout_height="match_parent"
                android:gravity="center"
                android:text="RM0000"
                android:textColor="@color/white"
                android:textSize="14sp"
                android:textStyle="bold" />

            <View
                android:layout_width="1dp"
                android:layout_height="46dp"
                android:layout_marginHorizontal="5dp"
                android:background="@color/border_strong" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeStop"
                style="@style/Widget.MaterialComponents.Button.TextButton"
                android:layout_width="64dp"
                android:layout_height="54dp"
                android:minWidth="0dp"
                android:text="END"
                android:textColor="#FF554D"
                android:textSize="13sp"
                android:textStyle="bold" />
        </LinearLayout>

'''
s = replace_section(s, live_start, live_end, live_panel)

p.write_text(s)
print('Applied Beta 1.4 single-group branding/UI patch')
