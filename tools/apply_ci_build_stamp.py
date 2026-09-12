#!/usr/bin/env python3
from pathlib import Path
import os

main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = main.read_text()
n = os.environ.get("GITHUB_RUN_NUMBER", "DEV")

# Locate Settings/help structurally. Do not depend on any particular title text,
# because production/offline materialization can rewrite it before this step.
fn = "    private fun showSettingsAndHelpDialog() {"
start = s.find(fn)
if start < 0:
    raise SystemExit("Settings function not found")
end = s.find("\n    private fun ", start + len(fn))
if end < 0:
    end = len(s)
segment = s[start:end]

build_text = f"Build #{n} • Offline Mesh Low-Latency Test\\nVoice: Nearby P2P_CLUSTER + Opus 20ms\\n\\n"

# Put the build identity at the top of the Settings message. This works whether
# setMessage currently receives a literal, concatenation, helper call, or other expression.
if f"Build #{n} • Offline Mesh Low-Latency Test" not in segment:
    marker = ".setMessage("
    pos = segment.find(marker)
    if pos < 0:
        raise SystemExit("Settings message call not found")
    insert_at = pos + len(marker)
    segment = segment[:insert_at] + f'"{build_text}" + ' + segment[insert_at:]

s = s[:start] + segment + s[end:]
main.write_text(s)
print(f"Stamped RideMesh Build #{n} into Settings message")
