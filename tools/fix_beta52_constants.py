from pathlib import Path

p = Path('app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt')
s = p.read_text()

anchor = '        private const val MAP_RENDER_MIN_INTERVAL_MS = 500L\n'
if anchor not in s:
    raise SystemExit('Beta5.2 constants: MAP_RENDER_MIN_INTERVAL_MS anchor not found')

addition = ''
if 'private const val LOCATION_STATIONARY_HEARTBEAT_MS' not in s:
    addition += '        private const val LOCATION_STATIONARY_HEARTBEAT_MS = 5_000L\n'
if 'private const val LOCATION_SHARE_HEARTBEAT_CHECK_MS' not in s:
    addition += '        private const val LOCATION_SHARE_HEARTBEAT_CHECK_MS = 1_000L\n'

if addition:
    s = s.replace(anchor, anchor + addition, 1)
    p.write_text(s)

print('Beta5.2 heartbeat constant declarations ensured')
