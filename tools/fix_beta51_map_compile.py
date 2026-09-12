from pathlib import Path

p = Path('app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt')
s = p.read_text()

# Google Maps SDK exposes MapStyleOptions from the model package.
s = s.replace(
    'import com.google.android.gms.maps.MapStyleOptions\n',
    'import com.google.android.gms.maps.model.MapStyleOptions\n',
)

# Keep map painting secondary to voice/reconnection. Location packets may arrive
# around once per second per rider, but the visible map needs at most 2 refreshes/s.
if 'private var lastMapRenderMs = 0L' not in s:
    anchor = '    private var lastMapFitMs = 0L\n'
    if anchor not in s:
        raise SystemExit('lastMapFitMs anchor missing')
    s = s.replace(anchor, anchor + '    private var lastMapRenderMs = 0L\n', 1)

old = '''    private fun renderLiveRiderMap(fitGroup: Boolean) {\n        val map = liveMap ?: return\n        val mine = myLiveLocation\n        val now = System.currentTimeMillis()\n'''
new = '''    private fun renderLiveRiderMap(fitGroup: Boolean) {\n        val map = liveMap ?: return\n        val now = System.currentTimeMillis()\n        if (!fitGroup && now - lastMapRenderMs < MAP_RENDER_MIN_INTERVAL_MS) return\n        lastMapRenderMs = now\n        val mine = myLiveLocation\n'''
if new not in s:
    if old not in s:
        raise SystemExit('renderLiveRiderMap anchor missing')
    s = s.replace(old, new, 1)

if 'private const val MAP_RENDER_MIN_INTERVAL_MS = 500L' not in s:
    anchor = '        private const val MAP_AUTO_FIT_COOLDOWN_MS = 5_000L\n'
    if anchor not in s:
        raise SystemExit('map constant anchor missing')
    s = s.replace(anchor, anchor + '        private const val MAP_RENDER_MIN_INTERVAL_MS = 500L\n', 1)

p.write_text(s)
print('Beta5.1 map compile/import fix + 500ms UI render throttle applied')
