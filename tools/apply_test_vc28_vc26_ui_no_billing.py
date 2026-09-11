from pathlib import Path
import re

# vc28 TEST: keep the proven vc26 Active UI exactly, but bypass Google Play billing
# for field testing. Do not redesign or replace the vc26 layout.

gradle = Path("app/build.gradle.kts")
s = gradle.read_text()
if 'versionCode = 26' not in s or 'versionName = "1.0.1"' not in s:
    raise SystemExit('Expected vc26 version identity not found')
s = s.replace('versionCode = 26', 'versionCode = 28', 1)
s = s.replace('versionName = "1.0.1"', 'versionName = "1.0.1-test28"', 1)
gradle.write_text(s)

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = main.read_text()

# Disable BillingClient startup entirely in this TEST build. The production vc26
# branch remains untouched and continues to use Google Play Billing.
billing_init_pattern = re.compile(
    r'\n\s*billingManager = RideMeshBillingManager\(.*?\n\s*billingManager\.start\(\)\n',
    re.S,
)
s, count = billing_init_pattern.subn(
    '\n        // VC28_TEST_NO_BILLING: BillingClient intentionally not started in field-test build.\n',
    s,
    count=1,
)
if count != 1:
    raise SystemExit(f'Expected one BillingManager startup block, replaced {count}')

# Replace only the entitlement gate. All create/join/start ride paths therefore
# continue through the original vc26 flow without opening the Premium screen.
access_pattern = re.compile(
    r'    private fun ensurePremiumAccess\(\): Boolean \{.*?\n    \}\n\n    private fun showPremiumPaywall\(\)',
    re.S,
)
replacement = '''    private fun ensurePremiumAccess(): Boolean {
        // VC28_TEST_NO_BILLING_GATE
        premiumEntryAction = PremiumEntryAction.NONE
        return true
    }

    private fun showPremiumPaywall()'''
s, count = access_pattern.subn(replacement, s, count=1)
if count != 1:
    raise SystemExit(f'Expected one premium access gate, replaced {count}')

# Safety: if a stale path ever tries to show the paywall, keep it hidden and return home.
paywall_pattern = re.compile(
    r'    private fun showPremiumPaywall\(\) \{.*?\n    \}\n\n    private fun renderPremiumPage\(\)',
    re.S,
)
paywall_replacement = '''    private fun showPremiumPaywall() {
        // VC28_TEST_NO_BILLING_PAYWALL_DISABLED
        if (::binding.isInitialized) {
            binding.screenPremium.visibility = View.GONE
            showScreen(Screen.HOME)
        }
    }

    private fun renderPremiumPage()'''
s, count = paywall_pattern.subn(paywall_replacement, s, count=1)
if count != 1:
    raise SystemExit(f'Expected one premium paywall function, replaced {count}')

main.write_text(s)

# Do not touch activity_main.xml: vc28 must visually match vc26.
layout = Path("app/src/main/res/layout/activity_main.xml").read_text()
required = [
    'RIDE ACTIVE',
    'HANDS-FREE INTERCOM',
    'android:id="@+id/audioTile"',
]
for value in required:
    if value not in layout:
        raise SystemExit(f'vc26 Active UI marker missing: {value}')

# Build-time safeguards.
materialized = main.read_text()
for value in [
    'VC28_TEST_NO_BILLING',
    'VC28_TEST_NO_BILLING_GATE',
    'VC28_TEST_NO_BILLING_PAYWALL_DISABLED',
    'MAX_VISIBLE_RIDER_TILES = 8',
]:
    if value not in materialized:
        raise SystemExit(f'vc28 safeguard missing: {value}')

print('Applied vc28 TEST: vc26 Active UI retained, billing startup/paywall bypassed')
