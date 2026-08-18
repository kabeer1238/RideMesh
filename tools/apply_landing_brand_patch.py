from pathlib import Path

layout = Path("app/src/main/res/layout/activity_main.xml")
text = layout.read_text(encoding="utf-8")

old_header = '''            <LinearLayout
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
'''

new_header = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="66dp"
                android:gravity="center_vertical"
                android:orientation="horizontal">

                <ImageView
                    android:layout_width="62dp"
                    android:layout_height="62dp"
                    android:contentDescription="RideMesh logo"
                    android:scaleType="centerInside"
                    android:src="@drawable/ridemesh_icon" />

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

hero_logo = '''                <ImageView
                    android:layout_width="match_parent"
                    android:layout_height="88dp"
                    android:layout_marginTop="18dp"
                    android:contentDescription="RideMesh by Autopilot India"
                    android:scaleType="centerInside"
                    android:src="@drawable/ridemesh_logo" />

'''

changed = False
if old_header in text:
    text = text.replace(old_header, new_header, 1)
    changed = True
elif 'android:contentDescription="RideMesh logo"' not in text:
    raise SystemExit("Landing header marker not found")

if hero_logo in text:
    text = text.replace(hero_logo, "", 1)
    changed = True

if changed:
    layout.write_text(text, encoding="utf-8")
    print("RideMesh landing branding patch applied")
else:
    print("RideMesh landing branding already applied")
