from pathlib import Path
import re

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
m = main.read_text()

# Final production pass: strip any remaining rider-visible beta language.
m = m.replace('RideMesh Beta4 settings & help', 'RideMesh settings & help')
m = m.replace(
    'Beta4 uses Internet-only WebRTC + Opus. Offline / multi-hop modes are not active in this package so voice stability can be tested independently.',
    'RideMesh uses Internet-only WebRTC + Opus. Offline / multi-hop modes are not active in this release.'
)
m = m.replace(
    'RideMesh automatically yields microphone and playback when a normal phone call, WhatsApp call or another VoIP app takes Android audio focus, then resumes after the call.',
    'RideMesh automatically yields microphone and playback when a normal phone call or another VoIP app takes Android audio focus, then resumes after the call.'
)
m = m.replace(
    'Offline / multi-hop is intentionally disabled in this Beta4 package while we prioritize clear, stable group voice.',
    'Offline / multi-hop is currently disabled while we prioritize clear, stable group voice.'
)
m = m.replace('Bug reports: WhatsApp group or direct support +91 9188664823.', 'Support: salesautopilotindia@gmail.com')
m = m.replace('NOT CONFIGURED IN THIS BETA', 'NOT CONFIGURED')

# Replace legacy beta-access UI functions with inert production compatibility shims.
# Internal beta-named symbols are kept only to avoid invasive changes to the stable vc23 code path.
beta_block = r'''    private fun betaStatusSentence(): String = "Access: active"

    private fun refreshBetaAccessUi(showWarning: Boolean) {
        binding.betaExpiryStatus.visibility = View.GONE
    }

    private fun ensureBetaUsable(): Boolean = true

    private fun maybeShowBetaWarning(days: Long) = Unit

    private fun showBetaExpiredDialog() = Unit

    private fun expireActiveRide() = Unit

    private fun showOfflineDiagnosticsDialog() {'''
pattern = r'    private fun betaStatusSentence\(\): String \{.*?\n    private fun showOfflineDiagnosticsDialog\(\) \{'
m, count = re.subn(pattern, beta_block, m, count=1, flags=re.S)
if count != 1:
    raise SystemExit(f'Production beta UI cleanup failed: {count}')

# Rider contact actions should use the standard phone dialer/SMS only in production.
m = m.replace('showRiderCallOptions(location.phoneNumber)', 'openRiderDialer(location.phoneNumber)')
m = m.replace('showRiderMessageOptions(location.phoneNumber)', 'openRiderMessage(location.phoneNumber)')

# Remove the WhatsApp-specific rider contact helper block inserted by beta5.3.
contact_pattern = r'    private fun showRiderCallOptions\(phone: String\) \{.*?(?=    private fun openRiderDialer\(phone: String\) \{)'
m, removed = re.subn(contact_pattern, '', m, count=1, flags=re.S)
if removed not in (0, 1):
    raise SystemExit(f'Unexpected WhatsApp rider helper cleanup count: {removed}')

# The earlier production support patch already turns this implementation into email.
# Rename the remaining compatibility method so the production source no longer carries a WhatsApp support name.
m = m.replace('openWhatsAppBugReport()', 'openEmailSupport()')

# Remove obsolete WhatsApp support/group constants if they survived an older source layout.
m = re.sub(r'^\s*private const val SUPPORT_WHATSAPP = .*\n', '', m, flags=re.M)
m = re.sub(r'^\s*private const val BUG_REPORT_GROUP_URL = .*\n', '', m, flags=re.M)
m = re.sub(r'^\s*private const val COMMUNITY_URL = .*\n', '', m, flags=re.M)

main.write_text(m)

# Clean production layout text too. Older vc23 layout still carried beta copy even
# though the expiry view was hidden; remove it so it cannot reappear on any device.
layout = Path("app/src/main/res/layout/activity_main.xml")
s = layout.read_text()
s = s.replace('country code for WhatsApp', 'country code if applicable')
s = s.replace(
    'Add your email for your beta rider profile. No account, password, OTP or verification is required.',
    'Add your email to your RideMesh rider profile. No account, password, OTP or verification is required.'
)

# Remove the static legacy beta countdown text from the hidden compatibility TextView.
marker = 'android:id="@+id/betaExpiryStatus"'
pos = s.find(marker)
if pos >= 0:
    start = s.rfind('<TextView', 0, pos)
    end = s.find('/>', pos)
    if start >= 0 and end >= 0:
        block = s[start:end + 2]
        block = re.sub(r'\n\s*android:text="[^"]*"', '', block, count=1)
        if 'android:visibility="gone"' not in block:
            block = block.replace(marker, marker + '\n                android:visibility="gone"', 1)
        s = s[:start] + block + s[end + 2:]
layout.write_text(s)

# Fail immediately if any known rider-facing beta/WhatsApp strings survived this pass.
forbidden_main = [
    'RIDE MESH  •  BETA',
    'RideMesh Beta4 settings & help',
    'Beta access:',
    'BETA ACCESS',
    'BETA PERIOD ENDED',
    'RideMesh Beta •',
    'This tester build expires 60 days',
    'This RideMesh Beta build has reached its 60-day test limit',
    'NOT CONFIGURED IN THIS BETA',
    'WHATSAPP CALL',
    'WHATSAPP MESSAGE',
    'WhatsApp group',
    'WhatsApp bug',
    'WhatsApp call',
    'WhatsApp is not available on this device',
    'whatsapp://call?number=',
    'https://wa.me/',
    'chat.whatsapp.com',
    'com.whatsapp',
]
for value in forbidden_main:
    if value in m:
        raise SystemExit(f'Forbidden production UI string remains: {value}')

forbidden_layout = [
    'beta rider profile',
    'BETA ACCESS',
    '60 DAYS REMAINING',
    'BETA PERIOD ENDED',
    'WhatsApp',
]
for value in forbidden_layout:
    if value in s:
        raise SystemExit(f'Forbidden production layout string remains: {value}')

if 'salesautopilotindia@gmail.com' not in m:
    raise SystemExit('Production support email missing')

print('Final production cleanup applied: no rider-visible beta or WhatsApp UI remains')
