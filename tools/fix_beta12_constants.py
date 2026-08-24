from pathlib import Path

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
t = main.read_text(encoding="utf-8")
if 'private const val SPEAKING_HOLD_MS' not in t:
    marker = '    companion object {\n'
    constants = '''        private const val SELF_TILE_KEY = "self"\n        private const val MAX_VISIBLE_RIDER_TILES = 6\n        private const val SPEAKING_HOLD_MS = 560L\n'''
    if marker not in t:
        raise SystemExit("MainActivity companion object not found")
    t = t.replace(marker, marker + constants, 1)
main.write_text(t, encoding="utf-8")

audio = Path("app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt")
a = audio.read_text(encoding="utf-8")
old = '''    private fun ensureAudioFocus(): Boolean {\n        if (focusHeld.get() && !focusPaused.get()) return true\n        return when (audioManager.requestAudioFocus(audioFocusRequest)) {\n'''
new = '''    private fun ensureAudioFocus(): Boolean {\n        if (focusHeld.get() && focusPaused.get()) return false\n        if (focusHeld.get() && !focusPaused.get()) return true\n        return when (audioManager.requestAudioFocus(audioFocusRequest)) {\n'''
if old in a:
    a = a.replace(old, new, 1)
elif new not in a:
    raise SystemExit("Audio focus marker not found")
audio.write_text(a, encoding="utf-8")

print("Beta 1.2 constants/audio-focus fix applied")
