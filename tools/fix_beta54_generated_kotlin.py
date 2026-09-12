from pathlib import Path

p = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = p.read_text()

# The Beta5.4 regex materializer uses a replacement string, so the escaped newline
# in the Maps-key fallback can arrive as a literal source-code line break. Normalize
# it back to a legal Kotlin escaped newline.
broken_maps = '''                text = "GOOGLE MAPS KEY REQUIRED
Voice and rider location sharing remain available."
'''
fixed_maps = '''                text = "GOOGLE MAPS KEY REQUIRED\\nVoice and rider location sharing remain available."
'''
if broken_maps in s:
    s = s.replace(broken_maps, fixed_maps, 1)

# Normalize the cluster label text size to valid Kotlin.
s = s.replace('            textSize = dp(6).5f\n', '            textSize = dp(7).toFloat()\n')

# Fail early if either known malformed form survived.
if 'text = "GOOGLE MAPS KEY REQUIRED\nVoice and rider location sharing remain available."' in s:
    raise SystemExit("vc23 map fallback string still contains a raw source newline")
if 'textSize = dp(6).5f' in s:
    raise SystemExit("vc23 cluster label textSize is still malformed")

p.write_text(s)
print("Beta5.4 vc23 generated Kotlin compile fixes applied")
