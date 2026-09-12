from pathlib import Path
import re

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = main.read_text()

# The full-screen Premium patch runs after several historical UI materializers.
# Those patches may have changed the Screen enum, so do not rely on an exact
# string match. Extend the existing enum robustly and ensure the premium action
# state type exists before Kotlin compilation.

screen_pattern = re.compile(r'    private enum class Screen \{([^}]*)\}')
match = screen_pattern.search(s)
if not match:
    raise SystemExit('Premium compile fix: Screen enum not found')

members = [item.strip() for item in match.group(1).split(',') if item.strip()]
if 'PREMIUM' not in members:
    members.append('PREMIUM')
replacement = '    private enum class Screen { ' + ', '.join(members) + ' }'
s = s[:match.start()] + replacement + s[match.end():]

if 'private enum class PremiumEntryAction' not in s:
    anchor = replacement + '\n'
    enum_decl = '    private enum class PremiumEntryAction { NONE, CREATE_RIDE, JOIN_RIDE, START_RIDE }\n'
    if anchor not in s:
        raise SystemExit('Premium compile fix: Screen enum insertion anchor missing')
    s = s.replace(anchor, anchor + enum_decl, 1)

if 'private var premiumEntryAction = PremiumEntryAction.NONE' not in s:
    state_anchor = '    private var micMuted = false\n'
    if state_anchor not in s:
        raise SystemExit('Premium compile fix: premium state anchor missing')
    s = s.replace(
        state_anchor,
        state_anchor + '    private var premiumEntryAction = PremiumEntryAction.NONE\n',
        1,
    )

# Fail early if the generated source still cannot express the Premium screen.
required = [
    'private enum class PremiumEntryAction { NONE, CREATE_RIDE, JOIN_RIDE, START_RIDE }',
    'private var premiumEntryAction = PremiumEntryAction.NONE',
    'Screen.PREMIUM',
    'binding.screenPremium',
]
for value in required:
    if value not in s:
        raise SystemExit(f'Premium compile fix verification failed: {value}')

screen_match = screen_pattern.search(s)
if not screen_match or 'PREMIUM' not in [item.strip() for item in screen_match.group(1).split(',')]:
    raise SystemExit('Premium compile fix verification failed: PREMIUM screen member missing')

main.write_text(s)
print('Premium full-screen compile fix applied and verified')
