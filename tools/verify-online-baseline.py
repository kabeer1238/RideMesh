"""Verify original voice implementations; permit exactly one read-only Android status accessor."""
from pathlib import Path
import hashlib

accessor = b"    fun isAudioInterrupted(): Boolean = focusPaused\n"
android = "app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt"
for line in Path("tools/online-baseline.sha256").read_text().splitlines():
    digest, path = line.split(maxsplit=1)
    content = Path(path).read_bytes()
    if path == android:
        assert content.count(accessor) == 1, "Missing or changed read-only interruption accessor"
        content = content.replace(accessor, b"", 1)
    assert hashlib.sha256(content).hexdigest() == digest, f"Original online implementation changed: {path}"
    print(f"PASS: {path}")
