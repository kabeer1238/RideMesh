from pathlib import Path

p = Path("app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt")
s = p.read_text()

old = """        sourceQueues.clear()
        sourcePrimed.clear()
        sourceLastSeenMs.clear()
"""
new = """        sourceStates.clear()
"""

if old in s:
    s = s.replace(old, new, 1)
elif "        sourceStates.clear()\n" not in s:
    raise SystemExit("Beta3 AudioEngine cleanup anchor not found")

p.write_text(s)
print("Beta3 AudioEngine cleanup validated.")
