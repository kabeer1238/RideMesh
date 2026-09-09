#!/usr/bin/env python3
from pathlib import Path
import re

# Offline mesh development build only.
# Production billing scripts remain untouched; this patch runs AFTER them.
main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = main.read_text()

# Do not connect this offline test build to Google Play Billing.
s = s.replace("        billingManager.start()\n", "        // Offline mesh test build: Google Play Billing intentionally disabled.\n")

# Bypass the Premium gate while preserving the production code generated earlier.
pattern = re.compile(r"    private fun ensurePremiumAccess\(\): Boolean \{.*?\n    \}\n", re.S)
replacement = '''    private fun ensurePremiumAccess(): Boolean {
        // Offline mesh test build: all ride functions are directly accessible.
        premiumEntryAction = PremiumEntryAction.NONE
        return true
    }
'''
s, count = pattern.subn(replacement, s, count=1)
if count != 1:
    raise SystemExit("Offline no-subscription patch: ensurePremiumAccess() not found")

# Defensive: Premium page can never be displayed in this build.
s = s.replace(
    "        binding.screenPremium.visibility = if (screen == Screen.PREMIUM) View.VISIBLE else View.GONE\n",
    "        binding.screenPremium.visibility = View.GONE\n",
)

main.write_text(s)
print("Offline mesh test subscription gate disabled; Google Play Billing connection disabled")
