from pathlib import Path
import re

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = main.read_text()

# The beta5.5 patch historically relied on an exact Screen enum string. Earlier
# patch stages can change that declaration, so make PREMIUM insertion structural.
screen_pattern = re.compile(r'(private\s+enum\s+class\s+Screen\s*\{)([^}]*)(\})')
match = screen_pattern.search(s)
if not match:
    raise SystemExit('Premium enum fix failed: Screen enum not found')

entries = [item.strip() for item in match.group(2).split(',') if item.strip()]
if 'PREMIUM' not in entries:
    entries.append('PREMIUM')
replacement = match.group(1) + ' ' + ', '.join(entries) + ' ' + match.group(3)
s = s[:match.start()] + replacement + s[match.end():]

# Guarantee the action enum exists exactly once, regardless of how the earlier
# MainActivity source was shaped by previous materialization patches.
action_decl = 'private enum class PremiumEntryAction { NONE, CREATE_RIDE, JOIN_RIDE, START_RIDE }'
action_matches = list(re.finditer(r'private\s+enum\s+class\s+PremiumEntryAction\s*\{[^}]*\}', s))
if len(action_matches) > 1:
    first = action_matches[0]
    for extra in reversed(action_matches[1:]):
        s = s[:extra.start()] + s[extra.end():]
elif not action_matches:
    screen_match = screen_pattern.search(s)
    if not screen_match:
        raise SystemExit('Premium enum fix failed after Screen update')
    insert_at = screen_match.end()
    s = s[:insert_at] + '\n    ' + action_decl + s[insert_at:]

# Hard checks so CI fails here with a useful message instead of later Kotlin errors.
if 'PREMIUM' not in re.search(r'private\s+enum\s+class\s+Screen\s*\{([^}]*)\}', s).group(1):
    raise SystemExit('Premium enum fix verification failed: Screen.PREMIUM missing')
if s.count('private enum class PremiumEntryAction') != 1:
    raise SystemExit('Premium enum fix verification failed: PremiumEntryAction count != 1')

main.write_text(s)
print('Production premium enums normalized')
