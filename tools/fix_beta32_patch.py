from pathlib import Path

p = Path('app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt')
s = p.read_text()

bad = '''    }
    }

    private fun applyBatteryPolicy() {'''
good = '''    }

    private fun applyBatteryPolicy() {'''

if bad not in s:
    raise SystemExit('Beta3.2 restart-brace cleanup anchor not found')

p.write_text(s.replace(bad, good, 1))
print('Beta3.2 restart brace fixed')
