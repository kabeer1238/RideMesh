#!/usr/bin/env python3
from pathlib import Path
import os
import re

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = main.read_text()
n = os.environ.get("GITHUB_RUN_NUMBER", "DEV")

# Find the Settings/help dialog and stamp only that dialog. This is resilient to
# earlier production/offline patches changing the exact title/message wording.
fn = "    private fun showSettingsAndHelpDialog() {"
start = s.find(fn)
if start < 0:
    raise SystemExit("Settings function not found")
end = s.find("\n    private fun ", start + len(fn))
if end < 0:
    end = len(s)
segment = s[start:end]

segment, title_count = re.subn(
    r'\.setTitle\("[^"]*settings[^\"]*"\)',
    f'.setTitle("RideMesh Offline • Build #{n}")',
    segment,
    count=1,
    flags=re.IGNORECASE,
)
if title_count != 1:
    # Fallback: replace the first setTitle in this specific Settings function.
    segment, title_count = re.subn(
        r'\.setTitle\("[^"]*"\)',
        f'.setTitle("RideMesh Offline • Build #{n}")',
        segment,
        count=1,
    )
if title_count != 1:
    raise SystemExit("Settings title not found")

build_line = f'"Build: #{n} • Offline Mesh Low-Latency Test\\nVoice engine: Nearby P2P_CLUSTER + Opus 20ms\\n\\n" +\n                    '
if f'Build: #{n} • Offline Mesh Low-Latency Test' not in segment:
    marker = ".setMessage(\n                "
    if marker not in segment:
        raise SystemExit("Settings message start not found")
    segment = segment.replace(marker, ".setMessage(\n                " + build_line, 1)

s = s[:start] + segment + s[end:]
main.write_text(s)
print(f"Stamped RideMesh Build #{n} into Settings")
