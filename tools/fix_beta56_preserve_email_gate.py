from pathlib import Path

p = Path('app/src/main/res/layout/activity_main.xml')
s = p.read_text()

if '@+id/screenEmail' not in s:
    email_screen = r'''

    <!-- EMAIL / RIDER PROFILE GATE — preserved for Beta5.6 -->
    <ScrollView
        android:id="@+id/screenEmail"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:background="@color/black"
        android:fillViewport="true"
        android:visibility="gone">

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="match_parent"
            android:gravity="center_horizontal"
            android:orientation="vertical"
            android:paddingStart="24dp"
            android:paddingTop="34dp"
            android:paddingEnd="24dp"
            android:paddingBottom="28dp">

            <ImageView
                android:layout_width="match_parent"
                android:layout_height="104dp"
                android:contentDescription="RideMesh by Autopilot India"
                android:scaleType="fitCenter"
                android:src="@drawable/ridemesh_logo_exact" />

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="26dp"
                android:background="@drawable/home_hero_bg"
                android:orientation="vertical"
                android:padding="22dp">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="32dp"
                    android:background="@drawable/hero_badge_bg"
                    android:gravity="center"
                    android:paddingStart="12dp"
                    android:paddingEnd="12dp"
                    android:text="RIDER PROFILE"
                    android:textColor="@color/accent"
                    android:textSize="10sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="18dp"
                    android:fontFamily="sans-serif-condensed"
                    android:letterSpacing="0.04"
                    android:text="WELCOME TO\nRIDEMESH"
                    android:textColor="@color/white"
                    android:textSize="31sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="10dp"
                    android:lineSpacingExtra="3dp"
                    android:text="Add your email for your beta rider profile. No account, password, OTP or verification is required."
                    android:textColor="@color/muted"
                    android:textSize="13sp" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="24dp"
                    android:text="EMAIL ADDRESS"
                    android:textColor="@color/faint"
                    android:textSize="10sp"
                    android:textStyle="bold" />

                <EditText
                    android:id="@+id/emailInput"
                    android:layout_width="match_parent"
                    android:layout_height="56dp"
                    android:backgroundTint="@color/accent"
                    android:hint="you@example.com"
                    android:imeOptions="actionDone"
                    android:inputType="textEmailAddress"
                    android:maxLength="100"
                    android:singleLine="true"
                    android:textColor="@color/white"
                    android:textColorHint="@color/faint"
                    android:textSize="16sp" />

                <com.google.android.material.button.MaterialButton
                    android:id="@+id/emailSave"
                    android:layout_width="match_parent"
                    android:layout_height="56dp"
                    android:layout_marginTop="22dp"
                    android:text="SAVE &amp; CONTINUE"
                    android:textColor="@color/black"
                    android:textSize="12sp"
                    android:textStyle="bold"
                    app:backgroundTint="@color/accent"
                    app:cornerRadius="14dp" />
            </LinearLayout>
        </LinearLayout>
    </ScrollView>
'''
    if '</FrameLayout>' not in s:
        raise SystemExit('vc26 email fix: root closing tag not found')
    s = s.replace('</FrameLayout>', email_screen + '\n</FrameLayout>', 1)
    p.write_text(s)

print('Beta5.6 email/profile gate preserved')
