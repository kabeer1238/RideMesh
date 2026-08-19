from pathlib import Path

files = [
    Path('app/src/main/java/com/bikemesh/ridemesh/mesh/MeshNode.kt'),
    Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt'),
]

needle = '    private val nodeId = UUID.randomUUID()\n'
for path in files:
    text = path.read_text()
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f'{path}: expected one legacy nodeId declaration, found {count}')
    path.write_text(text.replace(needle, '', 1))
    print(f'Removed legacy nodeId from {path}')
