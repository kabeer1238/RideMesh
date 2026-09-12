from pathlib import Path
import re

internet = Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt')
s = internet.read_text()

# Beta4.9 keeps the validated vc16 voice, noise-aware ducking, codec, jitter,
# audio-route and call-priority behavior unchanged.  This patch only reduces
# avoidable CPU/network wakeups during long rides.

# Track whether the adaptive duck monitor is actively watching a music session.
state_anchor = '    @Volatile private var noiseCalibrationUntilMs = 0L\n'
if 'smartDuckMusicWasActive' not in s:
    if state_anchor not in s:
        raise SystemExit('Beta4.8 noise-aware state anchor not found')
    s = s.replace(
        state_anchor,
        state_anchor + '    @Volatile private var smartDuckMusicWasActive = false\n',
        1,
    )

# Replace the fixed 150 ms getStats loop with adaptive polling.  When no music is
# playing we only perform a cheap AudioManager activity check and do not call
# WebRTC getStats at all.  When music starts, briefly relearn the current helmet/
# road noise floor, then use responsive polling.  While already ducked we can
# poll a little slower because the 900 ms hold window protects speech gaps.
start_pattern = re.compile(
    r'    private fun startSmartDucking\(\) \{.*?\n    \}\n\n    private fun stopSmartDucking',
    re.S,
)
start_replacement = r'''    private fun startSmartDucking() {
        stopSmartDucking(restoreVolume = true)
        lastVoiceActivityMs = 0L
        smartDuckStatsPending.set(false)
        localNoiseFloor = NOISE_FLOOR_INITIAL
        remoteNoiseFloor = NOISE_FLOOR_INITIAL
        localSpeechHits = 0
        remoteSpeechHits = 0
        noiseCalibrationUntilMs = System.currentTimeMillis() + NOISE_CALIBRATION_MS
        smartDuckMusicWasActive = false

        smartDuckThread = Thread({
            try {
                while (running.get() && !Thread.currentThread().isInterrupted) {
                    val manager = audioManager
                    val musicActive = manager?.isMusicActive == true || musicDucked

                    val sleepMs = when {
                        focusPaused || sessions.isEmpty() -> {
                            smartDuckMusicWasActive = false
                            localSpeechHits = 0
                            remoteSpeechHits = 0
                            restoreMusicVolume(manager)
                            SMART_DUCK_NO_MUSIC_POLL_MS
                        }

                        !musicActive -> {
                            if (smartDuckMusicWasActive) {
                                smartDuckMusicWasActive = false
                                localSpeechHits = 0
                                remoteSpeechHits = 0
                            }
                            restoreMusicVolume(manager)
                            SMART_DUCK_NO_MUSIC_POLL_MS
                        }

                        else -> {
                            if (!smartDuckMusicWasActive) {
                                smartDuckMusicWasActive = true
                                localNoiseFloor = NOISE_FLOOR_INITIAL
                                remoteNoiseFloor = NOISE_FLOOR_INITIAL
                                localSpeechHits = 0
                                remoteSpeechHits = 0
                                noiseCalibrationUntilMs = System.currentTimeMillis() +
                                    SMART_DUCK_MUSIC_CALIBRATION_MS
                            }
                            collectVoiceActivity()
                            applySmartDuckState()
                            if (musicDucked) {
                                SMART_DUCK_DUCKED_POLL_MS
                            } else {
                                SMART_DUCK_ACTIVE_POLL_MS
                            }
                        }
                    }

                    Thread.sleep(sleepMs)
                }
            } catch (_: InterruptedException) {
                // Ride stopped or restarted.
            } finally {
                smartDuckMusicWasActive = false
                restoreMusicVolume()
            }
        }, "RideMesh-SmartDuck").apply {
            isDaemon = true
            start()
        }
    }

    private fun stopSmartDucking'''
s, count = start_pattern.subn(start_replacement, s, count=1)
if count != 1:
    raise SystemExit('Beta4.8 startSmartDucking block not found')

# Adaptive presence heartbeat: a stable room does not need one MQTT presence
# publish every second.  New riders still converge quickly because every rider
# publishes immediately on connection and existing riders immediately answer a
# previously unseen presence (the Beta4.4 fast-presence behavior).
presence_old = '''            val now = System.currentTimeMillis()
            if (now - lastPresence >= PRESENCE_INTERVAL_MS) {
                publishPresence()
                refreshPeerNegotiation(now)
                prunePeers(now)
                lastPresence = now
            }
'''
presence_new = '''            val now = System.currentTimeMillis()
            val stableRoom = sessions.size >= peers.size && sessions.values.all { it.connected }
            val presenceIntervalMs = if (stableRoom) {
                PRESENCE_STABLE_INTERVAL_MS
            } else {
                PRESENCE_DISCOVERY_INTERVAL_MS
            }
            if (now - lastPresence >= presenceIntervalMs) {
                publishPresence()
                if (!stableRoom) refreshPeerNegotiation(now)
                prunePeers(now)
                lastPresence = now
            }
'''
if 'PRESENCE_STABLE_INTERVAL_MS' not in s:
    if presence_old not in s:
        raise SystemExit('Presence scheduling block not found')
    s = s.replace(presence_old, presence_new, 1)

# If signaling drops while the already-established WebRTC voice path is still
# carrying the ride, back off MQTT retries further.  If voice is down too, retain
# the original faster recovery ceiling.
reconnect_old = '''    private fun nextReconnectDelayMs(): Long {
        val exponent = reconnectAttempt.coerceAtMost(3)
        val base = (RECONNECT_BASE_DELAY_MS * (1L shl exponent)).coerceAtMost(RECONNECT_MAX_DELAY_MS)
        reconnectAttempt = (reconnectAttempt + 1).coerceAtMost(8)
        return base + Random.nextLong(0L, RECONNECT_JITTER_MS + 1L)
    }
'''
reconnect_new = '''    private fun nextReconnectDelayMs(): Long {
        val voiceStillActive = voicePeerCount() > 0
        val exponent = reconnectAttempt.coerceAtMost(if (voiceStillActive) 4 else 3)
        val maxDelay = if (voiceStillActive) {
            RECONNECT_MAX_DELAY_WITH_VOICE_MS
        } else {
            RECONNECT_MAX_DELAY_MS
        }
        val base = (RECONNECT_BASE_DELAY_MS * (1L shl exponent)).coerceAtMost(maxDelay)
        reconnectAttempt = (reconnectAttempt + 1).coerceAtMost(8)
        return base + Random.nextLong(0L, RECONNECT_JITTER_MS + 1L)
    }
'''
if 'RECONNECT_MAX_DELAY_WITH_VOICE_MS' not in s:
    if reconnect_old not in s:
        raise SystemExit('Signaling reconnect block not found')
    s = s.replace(reconnect_old, reconnect_new, 1)

# Constants: preserve the proven 22% duck level, 900 ms hold, all WebRTC media
# values and the 14 s peer timeout.  Only scheduling/wakeup values change.
if 'private const val SMART_DUCK_POLL_MS = 150L' not in s:
    raise SystemExit('Expected vc16 smart-duck poll constant not found')
s = s.replace(
    '        private const val SMART_DUCK_POLL_MS = 150L\n',
    '        private const val SMART_DUCK_NO_MUSIC_POLL_MS = 500L\n'
    '        private const val SMART_DUCK_ACTIVE_POLL_MS = 200L\n'
    '        private const val SMART_DUCK_DUCKED_POLL_MS = 300L\n'
    '        private const val SMART_DUCK_MUSIC_CALIBRATION_MS = 600L\n',
    1,
)

if 'private const val PRESENCE_INTERVAL_MS = 1_000L' not in s:
    raise SystemExit('Expected vc16 1s presence interval not found')
s = s.replace(
    '        private const val PRESENCE_INTERVAL_MS = 1_000L\n',
    '        private const val PRESENCE_DISCOVERY_INTERVAL_MS = 1_000L\n'
    '        private const val PRESENCE_STABLE_INTERVAL_MS = 3_000L\n',
    1,
)

# Presence traffic itself keeps MQTT active, so a 24 s ping remains safely below
# the 30 s MQTT keepalive while halving redundant explicit ping packets.
s = s.replace(
    '        private const val PING_INTERVAL_MS = 12_000L\n',
    '        private const val PING_INTERVAL_MS = 24_000L\n',
    1,
)

if 'private const val RECONNECT_MAX_DELAY_WITH_VOICE_MS' not in s:
    s = s.replace(
        '        private const val RECONNECT_MAX_DELAY_MS = 8_000L\n',
        '        private const val RECONNECT_MAX_DELAY_MS = 8_000L\n'
        '        private const val RECONNECT_MAX_DELAY_WITH_VOICE_MS = 16_000L\n',
        1,
    )

internet.write_text(s)

# Separate version so vc16 stays a clean rollback point.
gradle = Path('app/build.gradle.kts')
g = gradle.read_text()
if 'versionCode = 17' not in g:
    if 'versionCode = 16' not in g:
        raise SystemExit('Expected vc16 versionCode before Beta4.9 patch')
    g = g.replace('versionCode = 16', 'versionCode = 17', 1)
if 'versionName = "1.0.0-beta4.9-battery-optimized"' not in g:
    g, count = re.subn(
        r'versionName = "1\.0\.0-beta4\.8-noise-aware-duck"',
        'versionName = "1.0.0-beta4.9-battery-optimized"',
        g,
        count=1,
    )
    if count != 1:
        raise SystemExit('Expected Beta4.8 versionName before Beta4.9 patch')
gradle.write_text(g)

print('Beta4.9 battery optimization applied: adaptive duck polling + stable presence + signaling backoff, vc17')
