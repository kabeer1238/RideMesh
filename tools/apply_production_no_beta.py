from pathlib import Path

# Production cleanup: no beta expiry enforcement and no beta UI/version text.

# Make the legacy beta window permanently non-expiring. Keeping the object avoids
# invasive changes to older stable vc23 code paths while guaranteeing that the
# 60-day timer can never disable a paid/trial subscriber.
beta = Path("app/src/main/java/com/bikemesh/ridemesh/beta/BetaWindow.kt")
beta.write_text('''package com.bikemesh.ridemesh.beta\n\nobject BetaWindow {\n    const val DURATION_DAYS = 60L\n    const val DAY_MS = 24L * 60L * 60L * 1000L\n    const val DURATION_MS = DURATION_DAYS * DAY_MS\n\n    fun expiresAt(firstLaunchMs: Long): Long = Long.MAX_VALUE\n    fun isExpired(firstLaunchMs: Long, nowMs: Long): Boolean = false\n    fun remainingDays(firstLaunchMs: Long, nowMs: Long): Long = DURATION_DAYS\n    fun warningBucket(daysRemaining: Long): Int? = null\n}\n''')

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
