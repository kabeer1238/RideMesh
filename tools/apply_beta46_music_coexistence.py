from pathlib import Path
import re

internet = Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt')
s = internet.read_text()

# Keep the stable vc13 WebRTC/Opus engine intact. Beta4.6 changes only Android
# audio-focus policy so media can coexist while calls still take priority.
field_anchor = '    private val reconnects = AtomicInteger(0)\n'
if 'mediaFocusRecoveryPending' not in s:
    if field_anchor not in s:
        raise SystemExit('InternetNode field anchor not found')
    s = s.replace(
        field_anchor,
        field_anchor + '    private val mediaFocusRecoveryPending = AtomicBoolean(false)\n',
        1,
    )

start = s.find('    private fun requestAudioFocus() {')
end = s.find('    private fun abandonAudioFocus() {', start)
if start < 0 or end < 0:
    raise SystemExit('Audio focus block not found')

new_focus = '''    private fun requestAudioFocus() {
        val manager = audioManager ?: return
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()

        val focusListener = AudioManager.OnAudioFocusChangeListener { change ->
            when (change) {
                AudioManager.AUDIOFOCUS_GAIN -> resumeAfterExternalAudio()

                // Phone/VoIP style interruptions are normally transient. RideMesh yields
                // completely, releases the communication route, and auto-resumes later.
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> pauseForExternalAudio()

                // Navigation/prompts that only ask us to duck must not tear down the ride.
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> {
                    if (!focusPaused && running.get()) {
                        audioStatus = if (userMuted) {
                            "MIC MUTED • MUSIC / NAV MIX ACTIVE"
                        } else {
                            "VOICE CONNECTED • MUSIC / NAV MIX ACTIVE"
                        }
                        listener.onInternetAudioStatus(audioStatus)
                    }
                }

                // A normal media player commonly asks for long-lived GAIN. Re-acquire
                // MAY_DUCK focus after a tiny settle period so the music app can stay
                // playing at reduced volume while RideMesh voice remains live.
                AudioManager.AUDIOFOCUS_LOSS -> recoverMusicMixFocus()
            }
        }

        audioFocusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
            .setAudioAttributes(attributes)
            .setAcceptsDelayedFocusGain(true)
            .setWillPauseWhenDucked(false)
            .setOnAudioFocusChangeListener(focusListener)
            .build()

        val result = manager.requestAudioFocus(audioFocusRequest!!)
        focusPaused = result != AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        applyVoiceEnabled()
        if (!focusPaused) {
            audioStatus = if (userMuted) {
                "MIC MUTED • MUSIC MIX READY"
            } else {
                "VOICE CONNECTED • MUSIC MIX READY"
            }
            listener.onInternetAudioStatus(audioStatus)
        }
    }

    private fun recoverMusicMixFocus() {
        if (!running.get() || focusPaused) return
        if (!mediaFocusRecoveryPending.compareAndSet(false, true)) return

        Thread({
            try {
                Thread.sleep(MEDIA_FOCUS_RECOVERY_MS)
            } catch (_: InterruptedException) {
                mediaFocusRecoveryPending.set(false)
                return@Thread
            }

            mediaFocusRecoveryPending.set(false)
            if (!running.get() || focusPaused) return@Thread
            val manager = audioManager ?: return@Thread
            val request = audioFocusRequest ?: return@Thread

            when (manager.requestAudioFocus(request)) {
                AudioManager.AUDIOFOCUS_REQUEST_GRANTED -> {
                    applyVoiceEnabled()
                    audioStatus = if (userMuted) {
                        "MIC MUTED • MUSIC PLAYING"
                    } else {
                        "VOICE CONNECTED • MUSIC PLAYING"
                    }
                    listener.onInternetAudioStatus(audioStatus)
                }

                AudioManager.AUDIOFOCUS_REQUEST_DELAYED,
                AudioManager.AUDIOFOCUS_REQUEST_FAILED -> {
                    // A locked high-priority owner is much more likely to be a real
                    // phone/VoIP call than ordinary media. Yield instead of fighting it.
                    pauseForExternalAudio()
                }
            }
        }, "RideMesh-MediaFocus").apply {
            isDaemon = true
            start()
        }
    }

'''
s = s[:start] + new_focus + s[end:]

# Stop stale media-focus recovery work when the ride ends.
abandon_old = '''        audioFocusRequest = null
        focusPaused = false
    }
'''
abandon_new = '''        audioFocusRequest = null
        mediaFocusRecoveryPending.set(false)
        focusPaused = false
    }
'''
if abandon_old not in s:
    raise SystemExit('abandonAudioFocus tail not found')
s = s.replace(abandon_old, abandon_new, 1)

# Add a very short debounce before reclaiming MAY_DUCK focus after a media player starts.
if 'MEDIA_FOCUS_RECOVERY_MS' not in s:
    s, count = re.subn(
        r'(private const val CALL_RESUME_SETTLE_MS\s*=\s*\d+L\n)',
        r'\1        private const val MEDIA_FOCUS_RECOVERY_MS = 180L\n',
        s,
        count=1,
    )
    if count != 1:
        raise SystemExit('CALL_RESUME_SETTLE_MS anchor not found')

internet.write_text(s)

# Version this as a new APK field candidate. This script runs after the vc13 patch.
gradle = Path('app/build.gradle.kts')
g = gradle.read_text()
if 'versionCode = 14' not in g:
    if 'versionCode = 13' not in g:
        raise SystemExit('Expected vc13 versionCode before Beta4.6 patch')
    g = g.replace('versionCode = 13', 'versionCode = 14', 1)
if 'versionName = "1.0.0-beta4.6-music-mix"' not in g:
    g, count = re.subn(
        r'versionName = "1\.0\.0-beta4\.5-themed-ui"',
        'versionName = "1.0.0-beta4.6-music-mix"',
        g,
        count=1,
    )
    if count != 1:
        raise SystemExit('Expected Beta4.5 versionName before Beta4.6 patch')
gradle.write_text(g)

print('Beta4.6 music coexistence applied: media MAY_DUCK + transient call priority + vc14')
