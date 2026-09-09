from pathlib import Path
import re

# Production cleanup: no beta expiry enforcement, no beta UI/version text,
# and no WhatsApp support dependency.

# Make the legacy beta window permanently non-expiring. Keeping the object avoids
# invasive changes to older stable vc23 code paths while guaranteeing that the
# 60-day timer can never disable a paid/trial subscriber.
beta = Path("app/src/main/java/com/bikemesh/ridemesh/beta/BetaWindow.kt")
beta.write_text('''package com.bikemesh.ridemesh.beta\n\nobject BetaWindow {\n    const val DURATION_DAYS = 60L\n    const val DAY_MS = 24L * 60L * 60L * 1000L\n    const val DURATION_MS = DURATION_DAYS * DAY_MS\n\n    fun expiresAt(firstLaunchMs: Long): Long = Long.MAX_VALUE\n    fun isExpired(firstLaunchMs: Long, nowMs: Long): Boolean = false\n    fun remainingDays(firstLaunchMs: Long, nowMs: Long): Long = DURATION_DAYS\n    fun warningBucket(daysRemaining: Long): Int? = null\n}\n''')

# Replace legacy beta-window tests with production expectations. The old tests
# intentionally asserted 60-day expiry behavior and must not gate a production build.
test = Path("app/src/test/java/com/bikemesh/ridemesh/beta/BetaWindowTest.kt")
if test.exists():
    test.write_text('''package com.bikemesh.ridemesh.beta\n\nimport org.junit.Assert.assertEquals\nimport org.junit.Assert.assertFalse\nimport org.junit.Assert.assertNull\nimport org.junit.Test\n\nclass BetaWindowTest {\n    private val start = 1_700_000_000_000L\n\n    @Test fun productionNeverExpiresAtLegacyDeadline() {\n        val legacyExpiry = start + BetaWindow.DURATION_MS\n        assertFalse(BetaWindow.isExpired(start, legacyExpiry))\n        assertFalse(BetaWindow.isExpired(start, Long.MAX_VALUE))\n    }\n\n    @Test fun productionDoesNotShowExpiryWarnings() {\n        assertNull(BetaWindow.warningBucket(14))\n        assertNull(BetaWindow.warningBucket(7))\n        assertNull(BetaWindow.warningBucket(1))\n        assertNull(BetaWindow.warningBucket(0))\n    }\n\n    @Test fun compatibilityCountdownCannotReachZero() {\n        assertEquals(60L, BetaWindow.remainingDays(start, start))\n        assertEquals(60L, BetaWindow.remainingDays(start, start + 365L * BetaWindow.DAY_MS))\n    }\n}\n''')

# Remove every rider-visible beta reference introduced by the older themed/public UI
# patches. Keep internal class/function names only where changing them would be invasive.
main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
m = main.read_text()
m = m.replace('text = "RIDE MESH  •  BETA"', 'text = "RIDE MESH"')
m = m.replace('            addPanelSection(body, "Beta")\n            addPanelInfo(body, "Access", betaStatusSentence())\n\n', '')
m = m.replace('            addPanelInfo(body, "Beta access", betaStatusSentence())\n', '')
m = m.replace('No OTP or password is required in this beta.', 'No OTP or password is required.')

# Replace every rider-facing WhatsApp support label with email support.
m = m.replace('"WHATSAPP SUPPORT"', '"EMAIL SUPPORT"')
m = m.replace('"WHATSAPP GROUP"', '"EMAIL SUPPORT"')
m = m.replace('"RideMesh WhatsApp group"', '"RideMesh support email"')

# Ensure Android Build details are available for the diagnostic email body.
if 'import android.os.Build\n' not in m:
    if 'import android.os.Bundle\n' in m:
        m = m.replace('import android.os.Bundle\n', 'import android.os.Build\nimport android.os.Bundle\n', 1)
    else:
        raise SystemExit('Could not add android.os.Build import')

# Replace the old WhatsApp launcher functions with an email-only support flow.
email_support = r'''    private fun openWhatsAppBugReport() {
        val diag = internetNode.diagnostics()
        val rideCode = normalizedRideCode().ifBlank { "Not active" }
        val connection = when {
            diag.voicePeersConnected > 0 -> "Connected"
            diag.signalingConnected -> "Ready"
            else -> "Reconnecting"
        }
        val voice = when {
            micMuted -> "Muted"
            diag.voicePeersConnected > 0 -> "Connected"
            else -> "Ready"
        }
        val appVersion = runCatching {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "Unknown"
        }.getOrDefault("Unknown")
        val subject = "RideMesh Support"
        val body = buildString {
            appendLine("Please describe your issue below:")
            appendLine()
            appendLine("--------------------------------")
            appendLine("RideMesh diagnostic information")
            appendLine("App version: $appVersion")
            appendLine("Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
            appendLine("Device: ${Build.MANUFACTURER} ${Build.MODEL}")
            appendLine("Ride code: $rideCode")
            appendLine("Connection: $connection")
            appendLine("Voice: $voice")
            appendLine("Visible riders: ${(diag.knownRiders + 1).coerceAtLeast(1)}")
            appendLine("--------------------------------")
        }
        val mailUri = Uri.parse(
            "mailto:$SUPPORT_EMAIL?subject=${Uri.encode(subject)}&body=${Uri.encode(body)}"
        )
        val intent = Intent(Intent.ACTION_SENDTO, mailUri)
        runCatching {
            startActivity(Intent.createChooser(intent, "Email RideMesh Support"))
        }.onFailure {
            Toast.makeText(this, "No email app found", Toast.LENGTH_LONG).show()
        }
    }

    private fun openRideMeshCommunity() {
        openWhatsAppBugReport()
    }'''
pattern = r'    private fun openWhatsAppBugReport\(\) \{.*?\n    \}\n\n    private fun openRideMeshCommunity\(\) \{.*?\n    \}'
m, count = re.subn(pattern, email_support, m, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f'Email support function replacement failed: {count}')

# Add the support email constant without exposing any WhatsApp URL in the public flow.
if 'private const val SUPPORT_EMAIL = "salesautopilotindia@gmail.com"' not in m:
    anchor = '        private const val USER_EMAIL_KEY = "user_email_v1"\n'
    if anchor not in m:
        raise SystemExit('Support email constant anchor not found')
    m = m.replace(
        anchor,
        anchor + '        private const val SUPPORT_EMAIL = "salesautopilotindia@gmail.com"\n',
        1,
    )

main.write_text(m)

# Hide the legacy beta-access line while retaining the view id for compatibility
# with older MainActivity bindings.
layout = Path("app/src/main/res/layout/activity_main.xml")
s = layout.read_text()
marker = 'android:id="@+id/betaExpiryStatus"'
pos = s.find(marker)
if pos >= 0:
    start = s.rfind('<TextView', 0, pos)
    end = s.find('/>', pos)
    if start >= 0 and end >= 0:
        block = s[start:end + 2]
        if 'android:visibility="gone"' not in block:
            block = block.replace(marker, marker + '\n                android:visibility="gone"', 1)
            s = s[:start] + block + s[end + 2:]
layout.write_text(s)

# Public version name should not expose internal beta naming.
gradle = Path("app/build.gradle.kts")
g = gradle.read_text()
g = g.replace('versionName = "1.0.0-beta5.5-subscription-paywall"', 'versionName = "1.0.0"')
gradle.write_text(g)
