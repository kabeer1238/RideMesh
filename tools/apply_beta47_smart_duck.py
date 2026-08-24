from pathlib import Path
import re

internet = Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt')
s = internet.read_text()

# Beta4.7 keeps the validated vc14 coexistence/focus policy and adds an explicit
# RideMesh-controlled music-volume duck. Android audio focus alone did not lower
# media volume on the field-test phones, so voice activity from WebRTC stats now
# drives STREAM_MUSIC attenuation locally on each rider's phone.

# One in-flight getStats collection at a time.
field_anchor = '    private val mediaFocusRecoveryPending = AtomicBoolean(false)\n'
if 'smartDuckStatsPending' not in s:
    if field_anchor not in s:
        raise SystemExit('Beta4.6 media focus field anchor not found')
    s = s.replace(
        field_anchor,
        field_anchor + '    private val smartDuckStatsPending = AtomicBoolean(false)\n',
        1,
    )

state_anchor = '    @Volatile private var audioStatus = "WEBRTC AUDIO READY"\n'
if 'smartDuckThread' not in s:
    if state_anchor not in s:
        raise SystemExit('Audio status state anchor not found')
    s = s.replace(
        state_anchor,
        state_anchor
        + '    @Volatile private var smartDuckThread: Thread? = null\n'
        + '    @Volatile private var lastVoiceActivityMs = 0L\n'
        + '    @Volatile private var musicVolumeBeforeDuck: Int? = null\n'
        + '    @Volatile private var musicDuckTargetVolume: Int? = null\n'
        + '    @Volatile private var musicDucked = false\n',
        1,
    )

start_anchor = '''        requestAudioFocus()
        selectAudioRoute()
        applyVoiceEnabled()

        listener.onInternetState(false, "WEBRTC SIGNALING CONNECTING • OPUS VOICE")
'''
if 'startSmartDucking()' not in s:
    if start_anchor not in s:
        raise SystemExit('Ride start audio anchor not found')
    s = s.replace(
        start_anchor,
        '''        requestAudioFocus()
        selectAudioRoute()
        applyVoiceEnabled()
        startSmartDucking()

        listener.onInternetState(false, "WEBRTC SIGNALING CONNECTING • OPUS VOICE")
''',
        1,
    )

stop_anchor = '''        abandonAudioFocus()
        clearCommunicationRoute()
'''
if 'stopSmartDucking(restoreVolume = true)' not in s:
    if stop_anchor not in s:
        raise SystemExit('Ride stop audio anchor not found')
    s = s.replace(
        stop_anchor,
        '''        stopSmartDucking(restoreVolume = true)
        abandonAudioFocus()
        clearCommunicationRoute()
''',
        1,
    )

insert_anchor = '    private fun applyVoiceEnabled() {\n'
if 'private fun startSmartDucking()' not in s:
    if insert_anchor not in s:
        raise SystemExit('applyVoiceEnabled anchor not found')

    smart_duck = r'''    private fun startSmartDucking() {
        stopSmartDucking(restoreVolume = true)
        lastVoiceActivityMs = 0L
        smartDuckStatsPending.set(false)

        smartDuckThread = Thread({
            try {
                while (running.get() && !Thread.currentThread().isInterrupted) {
                    if (focusPaused || sessions.isEmpty()) {
                        restoreMusicVolume()
                    } else {
                        collectVoiceActivity()
                        applySmartDuckState()
                    }
                    Thread.sleep(SMART_DUCK_POLL_MS)
                }
            } catch (_: InterruptedException) {
                // Ride stopped or restarted.
            } finally {
                restoreMusicVolume()
            }
        }, "RideMesh-SmartDuck").apply {
            isDaemon = true
            start()
        }
    }

    private fun stopSmartDucking(restoreVolume: Boolean) {
        smartDuckThread?.interrupt()
        smartDuckThread = null
        smartDuckStatsPending.set(false)
        if (restoreVolume) restoreMusicVolume()
    }

    private fun collectVoiceActivity() {
        val activeSessions = sessions.values.toList()
        if (activeSessions.isEmpty()) return
        if (!smartDuckStatsPending.compareAndSet(false, true)) return

        val remaining = AtomicInteger(activeSessions.size)
        activeSessions.forEach { session ->
            runCatching {
                session.pc.getStats { report ->
                    try {
                        val voiceActive = report.statsMap.values.any { stat ->
                            if (stat.type != "inbound-rtp" && stat.type != "media-source") {
                                false
                            } else {
                                val members = stat.members
                                val kind = (members["kind"] ?: members["mediaType"])?.toString().orEmpty()
                                val level = (members["audioLevel"] as? Number)?.toDouble() ?: 0.0
                                kind.equals("audio", ignoreCase = true) && level >= SMART_DUCK_AUDIO_LEVEL
                            }
                        }
                        if (voiceActive) lastVoiceActivityMs = System.currentTimeMillis()
                    } finally {
                        if (remaining.decrementAndGet() == 0) smartDuckStatsPending.set(false)
                    }
                }
            }.onFailure {
                if (remaining.decrementAndGet() == 0) smartDuckStatsPending.set(false)
            }
        }
    }

    private fun applySmartDuckState() {
        val manager = audioManager ?: return
        if (!manager.isMusicActive) {
            restoreMusicVolume(manager)
            return
        }

        val now = System.currentTimeMillis()
        val voiceActive = lastVoiceActivityMs > 0L &&
            now - lastVoiceActivityMs <= SMART_DUCK_HOLD_MS

        if (voiceActive) {
            duckMusicVolume(manager)
        } else {
            restoreMusicVolume(manager)
        }
    }

    private fun duckMusicVolume(manager: AudioManager) {
        if (musicDucked) return

        val current = runCatching {
            manager.getStreamVolume(AudioManager.STREAM_MUSIC)
        }.getOrNull() ?: return
        if (current <= 1) return

        val target = (current * SMART_DUCK_VOLUME_RATIO)
            .toInt()
            .coerceAtLeast(1)
            .coerceAtMost(current - 1)
        if (target >= current) return

        val changed = runCatching {
            manager.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)
            true
        }.getOrDefault(false)
        if (!changed) return

        musicVolumeBeforeDuck = current
        musicDuckTargetVolume = target
        musicDucked = true
        audioStatus = if (userMuted) {
            "MIC MUTED • RIDER TALKING • MUSIC LOWERED"
        } else {
            "VOICE ACTIVE • MUSIC LOWERED"
        }
        listener.onInternetAudioStatus(audioStatus)
    }

    private fun restoreMusicVolume(manager: AudioManager? = audioManager) {
        val original = musicVolumeBeforeDuck
        val target = musicDuckTargetVolume
        val wasDucked = musicDucked

        musicVolumeBeforeDuck = null
        musicDuckTargetVolume = null
        musicDucked = false

        if (!wasDucked || original == null || manager == null) return

        // If the rider manually changed the media volume while it was ducked,
        // respect that adjustment instead of overwriting it with an old value.
        val current = runCatching {
            manager.getStreamVolume(AudioManager.STREAM_MUSIC)
        }.getOrNull()
        if (target != null && current != null && current != target) return

        runCatching {
            manager.setStreamVolume(AudioManager.STREAM_MUSIC, original, 0)
        }
        if (running.get() && !focusPaused) {
            audioStatus = if (userMuted) {
                "MIC MUTED • MUSIC NORMAL"
            } else {
                "VOICE CONNECTED • MUSIC NORMAL"
            }
            listener.onInternetAudioStatus(audioStatus)
        }
    }

'''
    s = s.replace(insert_anchor, smart_duck + insert_anchor, 1)

# Add constants beside the existing audio-focus timing constants.
constant_anchor = '        private const val MEDIA_FOCUS_RECOVERY_MS = 180L\n'
if 'SMART_DUCK_POLL_MS' not in s:
    if constant_anchor not in s:
        raise SystemExit('Beta4.6 media focus constant anchor not found')
    s = s.replace(
        constant_anchor,
        constant_anchor
        + '        private const val SMART_DUCK_POLL_MS = 150L\n'
        + '        private const val SMART_DUCK_HOLD_MS = 900L\n'
        + '        private const val SMART_DUCK_AUDIO_LEVEL = 0.012\n'
        + '        private const val SMART_DUCK_VOLUME_RATIO = 0.22\n',
        1,
    )

internet.write_text(s)

# STREAM_MUSIC volume control is a normal Android audio-settings permission.
manifest = Path('app/src/main/AndroidManifest.xml')
m = manifest.read_text()
if 'android.permission.MODIFY_AUDIO_SETTINGS' not in m:
    permission_anchor = '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n'
    if permission_anchor not in m:
        raise SystemExit('Manifest network permission anchor not found')
    m = m.replace(
        permission_anchor,
        permission_anchor + '    <uses-permission android:name="android.permission.MODIFY_AUDIO_SETTINGS" />\n',
        1,
    )
manifest.write_text(m)

# Version this as a separate APK field candidate. Runs after Beta4.6 (vc14).
gradle = Path('app/build.gradle.kts')
g = gradle.read_text()
if 'versionCode = 15' not in g:
    if 'versionCode = 14' not in g:
        raise SystemExit('Expected vc14 versionCode before Beta4.7 patch')
    g = g.replace('versionCode = 14', 'versionCode = 15', 1)
if 'versionName = "1.0.0-beta4.7-smart-duck"' not in g:
    g, count = re.subn(
        r'versionName = "1\.0\.0-beta4\.6-music-mix"',
        'versionName = "1.0.0-beta4.7-smart-duck"',
        g,
        count=1,
    )
    if count != 1:
        raise SystemExit('Expected Beta4.6 versionName before Beta4.7 patch')
gradle.write_text(g)

print('Beta4.7 smart duck applied: WebRTC voice activity lowers local STREAM_MUSIC, vc15')
