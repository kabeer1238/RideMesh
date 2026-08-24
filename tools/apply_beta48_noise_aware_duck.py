from pathlib import Path
import re

internet = Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt')
s = internet.read_text()

# Beta4.8 refines vc15 smart ducking for motorcycle noise.  We keep the proven
# vc15 STREAM_MUSIC attenuation path, but classify local and remote audio
# independently, learn their moving noise floors, ignore isolated spikes, and
# prefer WebRTC's voiceActivityFlag when a device exposes it in RTCStats.

state_anchor = '    @Volatile private var musicDucked = false\n'
if 'noiseCalibrationUntilMs' not in s:
    if state_anchor not in s:
        raise SystemExit('Beta4.7 smart-duck state anchor not found')
    s = s.replace(
        state_anchor,
        state_anchor
        + '    private val smartDuckLevelLock = Any()\n'
        + '    private var smartDuckRoundLocalMax = 0.0\n'
        + '    private var smartDuckRoundRemoteMax = 0.0\n'
        + '    private var smartDuckRoundLocalVadKnown = false\n'
        + '    private var smartDuckRoundRemoteVadKnown = false\n'
        + '    private var smartDuckRoundLocalVad = false\n'
        + '    private var smartDuckRoundRemoteVad = false\n'
        + '    @Volatile private var localNoiseFloor = NOISE_FLOOR_INITIAL\n'
        + '    @Volatile private var remoteNoiseFloor = NOISE_FLOOR_INITIAL\n'
        + '    @Volatile private var localSpeechHits = 0\n'
        + '    @Volatile private var remoteSpeechHits = 0\n'
        + '    @Volatile private var noiseCalibrationUntilMs = 0L\n',
        1,
    )

start_old = '''        lastVoiceActivityMs = 0L
        smartDuckStatsPending.set(false)

        smartDuckThread = Thread({
'''
start_new = '''        lastVoiceActivityMs = 0L
        smartDuckStatsPending.set(false)
        localNoiseFloor = NOISE_FLOOR_INITIAL
        remoteNoiseFloor = NOISE_FLOOR_INITIAL
        localSpeechHits = 0
        remoteSpeechHits = 0
        noiseCalibrationUntilMs = System.currentTimeMillis() + NOISE_CALIBRATION_MS

        smartDuckThread = Thread({
'''
if 'noiseCalibrationUntilMs = System.currentTimeMillis() + NOISE_CALIBRATION_MS' not in s:
    if start_old not in s:
        raise SystemExit('Beta4.7 smart-duck start anchor not found')
    s = s.replace(start_old, start_new, 1)

pattern = re.compile(
    r'    private fun collectVoiceActivity\(\) \{.*?\n    \}\n\n    private fun applySmartDuckState\(\) \{',
    re.S,
)

replacement = r'''    private fun collectVoiceActivity() {
        val activeSessions = sessions.values.toList()
        if (activeSessions.isEmpty()) return
        if (!smartDuckStatsPending.compareAndSet(false, true)) return

        synchronized(smartDuckLevelLock) {
            smartDuckRoundLocalMax = 0.0
            smartDuckRoundRemoteMax = 0.0
            smartDuckRoundLocalVadKnown = false
            smartDuckRoundRemoteVadKnown = false
            smartDuckRoundLocalVad = false
            smartDuckRoundRemoteVad = false
        }

        val remaining = AtomicInteger(activeSessions.size)
        activeSessions.forEach { session ->
            runCatching {
                session.pc.getStats { report ->
                    try {
                        var localMax = 0.0
                        var remoteMax = 0.0
                        var localVadKnown = false
                        var remoteVadKnown = false
                        var localVad = false
                        var remoteVad = false

                        report.statsMap.values.forEach { stat ->
                            if (stat.type != "inbound-rtp" && stat.type != "media-source") return@forEach
                            val members = stat.members
                            val kind = (members["kind"] ?: members["mediaType"])?.toString().orEmpty()
                            if (!kind.equals("audio", ignoreCase = true)) return@forEach

                            val level = (members["audioLevel"] as? Number)?.toDouble() ?: 0.0
                            val vad = members["voiceActivityFlag"] as? Boolean

                            if (stat.type == "media-source") {
                                localMax = maxOf(localMax, level)
                                if (vad != null) {
                                    localVadKnown = true
                                    localVad = localVad || vad
                                }
                            } else {
                                remoteMax = maxOf(remoteMax, level)
                                if (vad != null) {
                                    remoteVadKnown = true
                                    remoteVad = remoteVad || vad
                                }
                            }
                        }

                        synchronized(smartDuckLevelLock) {
                            smartDuckRoundLocalMax = maxOf(smartDuckRoundLocalMax, localMax)
                            smartDuckRoundRemoteMax = maxOf(smartDuckRoundRemoteMax, remoteMax)
                            smartDuckRoundLocalVadKnown = smartDuckRoundLocalVadKnown || localVadKnown
                            smartDuckRoundRemoteVadKnown = smartDuckRoundRemoteVadKnown || remoteVadKnown
                            smartDuckRoundLocalVad = smartDuckRoundLocalVad || localVad
                            smartDuckRoundRemoteVad = smartDuckRoundRemoteVad || remoteVad
                        }
                    } finally {
                        if (remaining.decrementAndGet() == 0) {
                            finalizeNoiseAwareVoiceRound()
                            smartDuckStatsPending.set(false)
                        }
                    }
                }
            }.onFailure {
                if (remaining.decrementAndGet() == 0) {
                    finalizeNoiseAwareVoiceRound()
                    smartDuckStatsPending.set(false)
                }
            }
        }
    }

    private fun finalizeNoiseAwareVoiceRound() {
        val snapshot = synchronized(smartDuckLevelLock) {
            NoiseAwareLevels(
                localLevel = smartDuckRoundLocalMax,
                remoteLevel = smartDuckRoundRemoteMax,
                localVadKnown = smartDuckRoundLocalVadKnown,
                remoteVadKnown = smartDuckRoundRemoteVadKnown,
                localVad = smartDuckRoundLocalVad,
                remoteVad = smartDuckRoundRemoteVad,
            )
        }

        val now = System.currentTimeMillis()
        if (now < noiseCalibrationUntilMs) {
            localNoiseFloor = updateNoiseFloor(localNoiseFloor, snapshot.localLevel, NOISE_CALIBRATION_ALPHA)
            remoteNoiseFloor = updateNoiseFloor(remoteNoiseFloor, snapshot.remoteLevel, NOISE_CALIBRATION_ALPHA)
            localSpeechHits = 0
            remoteSpeechHits = 0
            return
        }

        val localThreshold = maxOf(
            LOCAL_SPEECH_ABSOLUTE_MIN,
            localNoiseFloor * LOCAL_NOISE_MULTIPLIER,
            localNoiseFloor + LOCAL_NOISE_MARGIN,
        )
        val remoteThreshold = maxOf(
            REMOTE_SPEECH_ABSOLUTE_MIN,
            remoteNoiseFloor * REMOTE_NOISE_MULTIPLIER,
            remoteNoiseFloor + REMOTE_NOISE_MARGIN,
        )

        val localCandidate = if (snapshot.localVadKnown) {
            snapshot.localVad && snapshot.localLevel >= LOCAL_SPEECH_ABSOLUTE_MIN
        } else {
            snapshot.localLevel >= localThreshold
        }
        val remoteCandidate = if (snapshot.remoteVadKnown) {
            snapshot.remoteVad && snapshot.remoteLevel >= REMOTE_SPEECH_ABSOLUTE_MIN
        } else {
            snapshot.remoteLevel >= remoteThreshold
        }

        localSpeechHits = updateSpeechHits(localSpeechHits, localCandidate)
        remoteSpeechHits = updateSpeechHits(remoteSpeechHits, remoteCandidate)

        // Quiet/non-speech samples follow the environment fairly quickly. Elevated
        // samples move the baseline only very slowly so a spoken sentence does not
        // become the new noise floor, while sustained wind can still be relearned.
        localNoiseFloor = updateNoiseFloor(
            localNoiseFloor,
            snapshot.localLevel,
            if (localCandidate) NOISE_SLOW_RISE_ALPHA else NOISE_TRACK_ALPHA,
        )
        remoteNoiseFloor = updateNoiseFloor(
            remoteNoiseFloor,
            snapshot.remoteLevel,
            if (remoteCandidate) NOISE_SLOW_RISE_ALPHA else NOISE_TRACK_ALPHA,
        )

        if (localSpeechHits >= SPEECH_CONFIRM_HITS || remoteSpeechHits >= SPEECH_CONFIRM_HITS) {
            lastVoiceActivityMs = now
        }
    }

    private fun updateSpeechHits(current: Int, candidate: Boolean): Int {
        return if (candidate) {
            minOf(current + 1, SPEECH_CONFIRM_HITS + 3)
        } else {
            maxOf(0, current - 1)
        }
    }

    private fun updateNoiseFloor(current: Double, sample: Double, alpha: Double): Double {
        if (sample <= 0.0) return current
        val bounded = sample.coerceIn(NOISE_FLOOR_MIN, NOISE_FLOOR_MAX)
        return (current + alpha * (bounded - current)).coerceIn(NOISE_FLOOR_MIN, NOISE_FLOOR_MAX)
    }

    private data class NoiseAwareLevels(
        val localLevel: Double,
        val remoteLevel: Double,
        val localVadKnown: Boolean,
        val remoteVadKnown: Boolean,
        val localVad: Boolean,
        val remoteVad: Boolean,
    )

    private fun applySmartDuckState() {'''

s, count = pattern.subn(replacement, s, count=1)
if count != 1:
    raise SystemExit('Beta4.7 collectVoiceActivity block not found')

old_constants = '''        private const val SMART_DUCK_POLL_MS = 150L
        private const val SMART_DUCK_HOLD_MS = 900L
        private const val SMART_DUCK_AUDIO_LEVEL = 0.012
        private const val SMART_DUCK_VOLUME_RATIO = 0.22
'''
new_constants = '''        private const val SMART_DUCK_POLL_MS = 150L
        private const val SMART_DUCK_HOLD_MS = 900L
        private const val SMART_DUCK_VOLUME_RATIO = 0.22
        private const val NOISE_CALIBRATION_MS = 1_500L
        private const val NOISE_FLOOR_INITIAL = 0.004
        private const val NOISE_FLOOR_MIN = 0.001
        private const val NOISE_FLOOR_MAX = 0.30
        private const val NOISE_CALIBRATION_ALPHA = 0.30
        private const val NOISE_TRACK_ALPHA = 0.12
        private const val NOISE_SLOW_RISE_ALPHA = 0.012
        private const val LOCAL_SPEECH_ABSOLUTE_MIN = 0.018
        private const val REMOTE_SPEECH_ABSOLUTE_MIN = 0.012
        private const val LOCAL_NOISE_MULTIPLIER = 3.0
        private const val REMOTE_NOISE_MULTIPLIER = 2.5
        private const val LOCAL_NOISE_MARGIN = 0.010
        private const val REMOTE_NOISE_MARGIN = 0.007
        private const val SPEECH_CONFIRM_HITS = 2
'''
if 'private const val NOISE_CALIBRATION_MS' not in s:
    if old_constants not in s:
        raise SystemExit('Beta4.7 smart-duck constants not found')
    s = s.replace(old_constants, new_constants, 1)

internet.write_text(s)

# Version this separately so vc15 remains a known rollback/test point.
gradle = Path('app/build.gradle.kts')
g = gradle.read_text()
if 'versionCode = 16' not in g:
    if 'versionCode = 15' not in g:
        raise SystemExit('Expected vc15 versionCode before Beta4.8 patch')
    g = g.replace('versionCode = 15', 'versionCode = 16', 1)
if 'versionName = "1.0.0-beta4.8-noise-aware-duck"' not in g:
    g, count = re.subn(
        r'versionName = "1\.0\.0-beta4\.7-smart-duck"',
        'versionName = "1.0.0-beta4.8-noise-aware-duck"',
        g,
        count=1,
    )
    if count != 1:
        raise SystemExit('Expected Beta4.7 versionName before Beta4.8 patch')
gradle.write_text(g)

print('Beta4.8 noise-aware duck applied: adaptive local/remote noise floor + speech confirmation, vc16')
