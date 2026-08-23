from pathlib import Path
import re

ROOT = Path('.')


def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    return text.replace(old, new, 1)


def sub_once(text, pattern, replacement, label):
    if replacement in text:
        return text
    out, count = re.subn(pattern, lambda m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: pattern count {count}')
    return out


# -----------------------------------------------------------------------------
# MainActivity: replace fragile startup email dialog with an in-app branded gate,
# make Back background the app, persist ride code as it is typed, and distinguish
# CREATE vs JOIN setup actions.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

s = replace_once(
    s,
    'import androidx.activity.result.contract.ActivityResultContracts\n',
    'import androidx.activity.OnBackPressedCallback\nimport androidx.activity.result.contract.ActivityResultContracts\n',
    'back callback import',
)
s = replace_once(
    s,
    'import androidx.core.content.FileProvider\n',
    'import androidx.core.content.FileProvider\nimport androidx.core.widget.doAfterTextChanged\n',
    'text watcher import',
)

s = replace_once(
    s,
    '    private enum class Screen { HOME, SETUP, ACTIVE }\n',
    '    private enum class Screen { HOME, SETUP, ACTIVE }\n    private enum class SetupMode { CREATE, JOIN }\n',
    'setup mode enum',
)
s = replace_once(
    s,
    '    private var meshLabRole = MeshNode.LabRole.NORMAL\n',
    '    private var meshLabRole = MeshNode.LabRole.NORMAL\n    private var setupMode = SetupMode.CREATE\n',
    'setup mode state',
)

# Create / Join semantics.
s = replace_once(
    s,
    '''        binding.createRide.setOnClickListener {\n            if (!ensureBetaUsable()) return@setOnClickListener\n            binding.setupTitle.text = "CREATE RIDE"\n            binding.rideCode.setText(generateRideCode())\n            showScreen(Screen.SETUP)\n        }\n\n        binding.joinRide.setOnClickListener {\n            if (!ensureBetaUsable()) return@setOnClickListener\n            binding.setupTitle.text = "JOIN RIDE"\n            showScreen(Screen.SETUP)\n            binding.rideCode.requestFocus()\n        }''',
    '''        binding.createRide.setOnClickListener {\n            if (!ensureBetaUsable()) return@setOnClickListener\n            setupMode = SetupMode.CREATE\n            binding.setupTitle.text = "CREATE RIDE"\n            binding.startRide.text = "START RIDE"\n            binding.rideCode.setText(generateRideCode())\n            showScreen(Screen.SETUP)\n        }\n\n        binding.joinRide.setOnClickListener {\n            if (!ensureBetaUsable()) return@setOnClickListener\n            setupMode = SetupMode.JOIN\n            binding.setupTitle.text = "JOIN RIDE"\n            binding.startRide.text = "JOIN RIDE"\n            showScreen(Screen.SETUP)\n            binding.rideCode.requestFocus()\n        }''',
    'create join semantics',
)

# Replace Beta4.3 startup dialog initialization with branded screen + robust back behavior.
s = replace_once(
    s,
    '''        refreshBetaAccessUi(showWarning = true)\n        updateMuteUi()\n        binding.logView.visibility = View.GONE\n        mainHandler.post { ensureUserEmail() }\n    }''',
    '''        refreshBetaAccessUi(showWarning = true)\n        updateMuteUi()\n        binding.logView.visibility = View.GONE\n\n        binding.emailSave.setOnClickListener { saveEmailProfile() }\n        binding.rideCode.doAfterTextChanged { text ->\n            val value = text?.toString().orEmpty().trim().uppercase().take(12)\n            if (value.isNotBlank()) prefs.edit().putString("code", value).apply()\n        }\n\n        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {\n            override fun handleOnBackPressed() {\n                // Rider requirement: Back never tears down an active voice session or exits the app.\n                // The task moves to background; reopening returns to the same activity/ride state.\n                moveTaskToBack(true)\n            }\n        })\n\n        mainHandler.post { ensureUserEmail() }\n    }''',
    'startup UX',
)

# Replace AlertDialog email flow entirely. This also removes the most likely new startup
# lifecycle failure point introduced in Beta4.3.
s = sub_once(
    s,
    r'''    private fun savedUserEmail\(\): String =.*?    private fun showScreen''',
    '''    private fun savedUserEmail(): String =\n        prefs.getString(USER_EMAIL_KEY, "").orEmpty().trim()\n\n    private fun hasValidUserEmail(): Boolean =\n        Patterns.EMAIL_ADDRESS.matcher(savedUserEmail()).matches()\n\n    private fun ensureUserEmail(): Boolean {\n        if (hasValidUserEmail()) {\n            binding.screenEmail.visibility = View.GONE\n            return true\n        }\n        showEmailProfileScreen()\n        return false\n    }\n\n    private fun showEmailProfileScreen() {\n        binding.emailInput.setText(savedUserEmail())\n        binding.emailInput.error = null\n        binding.screenEmail.visibility = View.VISIBLE\n        binding.emailInput.requestFocus()\n    }\n\n    private fun saveEmailProfile() {\n        val email = binding.emailInput.text?.toString().orEmpty().trim().lowercase()\n        if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {\n            binding.emailInput.error = "Enter a valid email address"\n            binding.emailInput.requestFocus()\n            return\n        }\n        prefs.edit().putString(USER_EMAIL_KEY, email).apply()\n        binding.screenEmail.visibility = View.GONE\n    }\n\n    private fun showScreen''',
    'branded email screen flow',
)

# Settings now opens the branded email profile screen rather than an Android dialog.
s = s.replace(
    '.setNeutralButton("CHANGE EMAIL") { _, _ -> showEmailEntryDialog(required = false) }',
    '.setNeutralButton("CHANGE EMAIL") { _, _ -> showEmailProfileScreen() }',
)

# QR scan should clearly become JOIN flow.
s = replace_once(
    s,
    '''                binding.rideCode.setText(code)\n                saveSettings()\n                AlertDialog.Builder(this)\n                    .setTitle("Join $code?")''',
    '''                setupMode = SetupMode.JOIN\n                binding.setupTitle.text = "JOIN RIDE"\n                binding.startRide.text = "JOIN RIDE"\n                binding.rideCode.setText(code)\n                saveSettings()\n                AlertDialog.Builder(this)\n                    .setTitle("Join $code?")''',
    'QR join semantics',
)

# Invitation is a join action too.
s = replace_once(
    s,
    '''                .setPositiveButton("JOIN") { _, _ ->\n                    binding.rideCode.setText(rideCode)\n                    saveSettings()''',
    '''                .setPositiveButton("JOIN") { _, _ ->\n                    setupMode = SetupMode.JOIN\n                    binding.setupTitle.text = "JOIN RIDE"\n                    binding.startRide.text = "JOIN RIDE"\n                    binding.rideCode.setText(rideCode)\n                    saveSettings()''',
    'invite join semantics',
)

p.write_text(s)


# -----------------------------------------------------------------------------
# Branded email/profile screen. It is part of the same black/cyan UI instead of a
# system AlertDialog, so startup feels native to RideMesh and is lifecycle-stable.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/res/layout/activity_main.xml'
x = p.read_text()
email_screen = r'''

    <!-- EMAIL / RIDER PROFILE GATE -->
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
if '@+id/screenEmail' not in x:
    if '</FrameLayout>' not in x:
        raise SystemExit('email screen: root FrameLayout closing tag not found')
    x = x.replace('</FrameLayout>', email_screen + '\n</FrameLayout>', 1)
p.write_text(x)


# -----------------------------------------------------------------------------
# InternetNode: faster rider discovery/negotiation, faster reconnect and modest
# Opus/WebRTC quality tuning. No transport replacement and no new privacy surface.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt'
i = p.read_text()

i = i.replace('            audioJitterBufferMaxPackets = 50', '            audioJitterBufferMaxPackets = 30')
i = i.replace('            iceCandidatePoolSize = 2', '            iceCandidatePoolSize = 4')
i = i.replace('        runCatching { pc.setBitrate(24_000, 40_000, 64_000) }', '        runCatching { pc.setBitrate(24_000, 48_000, 80_000) }')

# Existing riders immediately answer a newcomer presence once. This eliminates the
# newcomer's wait for every existing rider's next heartbeat (previously up to 2 s).
i = replace_once(
    i,
    '''        notifyPeerCount(force = previous == null)\n        ensurePeer(presence.origin, allowOffer = true)\n    }''',
    '''        notifyPeerCount(force = previous == null)\n        ensurePeer(presence.origin, allowOffer = true)\n        if (previous == null) {\n            // Fast room convergence: tell the newcomer about us immediately instead of\n            // waiting for the next periodic presence heartbeat.\n            publishPresence()\n        }\n    }''',
    'fast presence response',
)

# Opus: retain FEC and mono, set a clear voice bitrate ceiling and avoid DTX onset clipping.
i = i.replace(
    'if (!fmtp.contains("stereo=", ignoreCase = true)) fmtp += ";stereo=0"',
    'if (!fmtp.contains("stereo=", ignoreCase = true)) fmtp += ";stereo=0"\n            if (!fmtp.contains("maxaveragebitrate=", ignoreCase = true)) fmtp += ";maxaveragebitrate=48000"\n            if (!fmtp.contains("usedtx=", ignoreCase = true)) fmtp += ";usedtx=0"',
)
i = i.replace(
    '"$fmtpPrefix minptime=10;useinbandfec=1;stereo=0"',
    '"$fmtpPrefix minptime=10;useinbandfec=1;stereo=0;maxaveragebitrate=48000;usedtx=0"',
)

# Faster presence, negotiation and recovery. Values remain conservative enough for 2-6 riders.
i = i.replace('private const val SOCKET_TIMEOUT_MS = 3_000', 'private const val SOCKET_TIMEOUT_MS = 1_000')
i = i.replace('private const val PRESENCE_INTERVAL_MS = 2_000L', 'private const val PRESENCE_INTERVAL_MS = 1_000L')
i = i.replace('private const val PRESENCE_TIMEOUT_MS = 14_000L', 'private const val PRESENCE_TIMEOUT_MS = 8_000L')
i = i.replace('private const val OFFER_RETRY_INTERVAL_MS = 4_000L', 'private const val OFFER_RETRY_INTERVAL_MS = 1_500L')
i = i.replace('private const val ICE_DISCONNECTED_GRACE_MS = 6_000L', 'private const val ICE_DISCONNECTED_GRACE_MS = 3_000L')
i = i.replace('private const val ICE_FAILED_RETRY_MS = 1_000L', 'private const val ICE_FAILED_RETRY_MS = 600L')
i = i.replace('private const val RECONNECT_BASE_DELAY_MS = 1_000L', 'private const val RECONNECT_BASE_DELAY_MS = 500L')
i = i.replace('private const val RECONNECT_MAX_DELAY_MS = 8_000L', 'private const val RECONNECT_MAX_DELAY_MS = 4_000L')
i = i.replace('private const val RECONNECT_JITTER_MS = 500L', 'private const val RECONNECT_JITTER_MS = 250L')

p.write_text(i)

print('Beta4.4 stability + UX + speed patch applied')
