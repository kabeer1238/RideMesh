from pathlib import Path

p = Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt')
s = p.read_text()

anchor = '        private const val RECONNECT_JITTER_MS = 500L\n'
declarations = '''
        private const val CONNECTION_HEALTH_POLL_MS = 4_000L
        private const val AUDIO_ROUTE_RECOVERY_MS = 550L
        private val AUDIO_ROUTE_RECOVERY_TOKEN = Any()

        private const val QUALITY_EXCELLENT_LOSS_PERCENT = 2.0
        private const val QUALITY_EXCELLENT_RTT_MS = 180.0
        private const val QUALITY_EXCELLENT_JITTER_MS = 25.0
        private const val QUALITY_POOR_LOSS_PERCENT = 7.0
        private const val QUALITY_POOR_RTT_MS = 450.0
        private const val QUALITY_POOR_JITTER_MS = 60.0

        private const val AUDIO_TIER_POOR = 1
        private const val AUDIO_TIER_GOOD = 2
        private const val AUDIO_TIER_EXCELLENT = 3
'''

if 'private const val CONNECTION_HEALTH_POLL_MS =' not in s:
    if anchor not in s:
        raise SystemExit('Beta5.0 constant insertion anchor not found')
    s = s.replace(anchor, anchor + declarations, 1)

p.write_text(s)
print('Beta5.0 reliability constant declarations ensured')
