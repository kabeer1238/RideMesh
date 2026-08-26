from pathlib import Path
import re

root = Path('.')

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)

# -----------------------------------------------------------------------------
# Build identity: APK-only field test, AAB deliberately deferred.
# -----------------------------------------------------------------------------
p = root / 'app/build.gradle.kts'
s = p.read_text()
s = replace_once(
    s,
    'versionCode = 2\n        versionName = "1.0.0-beta2"',
    'versionCode = 3\n        versionName = "1.0.0-beta3-audio"',
    'build version',
)
p.write_text(s)

# -----------------------------------------------------------------------------
# AudioEngine: exact 20 ms capture frames + adaptive jitter buffer + ordered
# playout + short packet-loss concealment + stale latency catch-up.
# -----------------------------------------------------------------------------
p = root / 'app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt'
s = p.read_text()

s = replace_once(s, 'import java.util.ArrayDeque\n', 'import java.util.ArrayDeque\nimport java.util.TreeMap\n', 'TreeMap import')
s = replace_once(s, 'import kotlin.math.PI\n', 'import kotlin.math.PI\nimport kotlin.math.abs\n', 'abs import')

old_fields = '''    /**
     * Incoming audio is kept per remote rider and mixed into one 20 ms output frame.
     * This prevents a three-rider call from serialising two remote 20 ms frames into
     * 40 ms of playback every 20 ms, which was the main source of growing delay/jitter.
     */
    private val sourceQueues = ConcurrentHashMap<String, ArrayDeque<ByteArray>>()
    private val sourcePrimed = ConcurrentHashMap.newKeySet<String>()
    private val sourceLastSeenMs = ConcurrentHashMap<String, Long>()
'''
new_fields = '''    private data class IncomingFrame(
        val sequence: Int,
        val timestampMs: Long,
        val arrivalMs: Long,
        val audio: ByteArray,
    )

    private class SourceState {
        val frames = TreeMap<Int, IncomingFrame>()
        var expectedSequence: Int? = null
        var primed = false
        var targetPrimeFrames = MIN_PRIME_FRAMES
        var jitterEwmaMs = 0.0
        var lastArrivalMs = 0L
        var lastSenderTimestampMs = 0L
        var lastSeenMs = 0L
        var lastGoodFrame: ByteArray? = null
        var consecutivePlc = 0
    }

    /**
     * Beta3 keeps an ordered adaptive jitter buffer for each rider. Good links stay at
     * about 40 ms of prebuffer; unstable links can expand toward 120 ms temporarily.
     */
    private val sourceStates = ConcurrentHashMap<String, SourceState>()
'''
s = replace_once(s, old_fields, new_fields, 'source state fields')

old_clear = '''    private fun clearRemoteAudio() {
        sourceQueues.values.forEach { queue -> synchronized(queue) { queue.clear() } }
        sourcePrimed.clear()
        sourceLastSeenMs.clear()
    }
'''
new_clear = '''    private fun clearRemoteAudio() {
        sourceStates.values.forEach { state ->
            synchronized(state) {
                state.frames.clear()
                state.expectedSequence = null
                state.primed = false
                state.lastGoodFrame = null
                state.consecutivePlc = 0
            }
        }
        sourceStates.clear()
    }
'''
s = replace_once(s, old_clear, new_clear, 'clearRemoteAudio')

old_capture = '''                    while (capturing.get()) {
                        val read = activeRecorder.read(frame, 0, frame.size)
                        if (read <= 0) continue

                        val raw = if (read == frame.size) frame.copyOf() else frame.copyOf(read)
                        val current = windFilter.process(raw)
                        val rms = pcmRms(current)
'''
new_capture = '''                    while (capturing.get()) {
                        // AudioRecord is allowed to return a partial buffer. Beta2 treated every
                        // partial read as a complete 20 ms packet, which can sound slow/choppy.
                        // Beta3 accumulates exactly one 20 ms frame before VAD/transmission.
                        var filled = 0
                        while (filled < frame.size && capturing.get()) {
                            val read = activeRecorder.read(
                                frame,
                                filled,
                                frame.size - filled,
                                AudioRecord.READ_BLOCKING,
                            )
                            if (read < 0) throw IllegalStateException("AudioRecord read error $read")
                            if (read == 0) continue
                            filled += read
                        }
                        if (filled != frame.size) continue

                        val current = windFilter.process(frame.copyOf())
                        val rms = pcmRms(current)
'''
s = replace_once(s, old_capture, new_capture, 'exact capture framing')

start_marker = '''    /**
     * Queue one remote rider independently. Each source is capped at ~60 ms so a weak
     * network cannot create seconds of old speech. Two frames are collected before a
     * source starts, giving a small jitter buffer without noticeable conversational lag.
     */
    fun playIncoming(sourceId: String, audio: ByteArray) {'''
end_marker = '''    internal fun mixFrames(frames: List<ByteArray>): ByteArray {'''
if start_marker not in s or end_marker not in s:
    raise SystemExit('playback block anchors not found')
start = s.index(start_marker)
end = s.index(end_marker)
new_playback = '''    /**
     * Add one sequenced 20 ms packet to the per-rider adaptive jitter buffer.
     * Sender timestamps are used only for inter-packet timing, never for wall-clock sync.
     */
    fun playIncoming(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {
        if (audio.isEmpty() || !playbackRunning.get() || focusPaused.get()) return
        val key = sourceId.ifBlank { "unknown" }
        val normalized = when {
            audio.size == FRAME_BYTES -> audio.copyOf()
            audio.size > FRAME_BYTES -> audio.copyOf(FRAME_BYTES)
            else -> audio.copyOf(FRAME_BYTES)
        }
        val now = System.currentTimeMillis()
        val state = sourceStates.computeIfAbsent(key) { SourceState() }

        synchronized(state) {
            if (state.lastArrivalMs > 0L && state.lastSenderTimestampMs > 0L) {
                val arrivalDelta = now - state.lastArrivalMs
                val senderDelta = timestampMs - state.lastSenderTimestampMs
                if (arrivalDelta in 0L..500L && senderDelta in 10L..200L) {
                    val sample = abs(arrivalDelta.toDouble() - senderDelta.toDouble())
                    state.jitterEwmaMs = if (state.jitterEwmaMs == 0.0) {
                        sample
                    } else {
                        (state.jitterEwmaMs * 0.88) + (sample * 0.12)
                    }
                    state.targetPrimeFrames = targetPrimeFrames(state.jitterEwmaMs)
                }
            }

            state.lastArrivalMs = now
            state.lastSenderTimestampMs = timestampMs
            state.lastSeenMs = now

            val expected = state.expectedSequence
            if (expected != null && sequence < expected - OLD_PACKET_TOLERANCE) return@synchronized
            if (!state.frames.containsKey(sequence)) {
                state.frames[sequence] = IncomingFrame(sequence, timestampMs, now, normalized)
            }

            while (state.frames.size > MAX_SOURCE_QUEUE_FRAMES) {
                state.frames.pollFirstEntry()
            }

            // If the receiver ever gets far behind, jump forward rather than playing old speech.
            if (state.primed && state.frames.size > state.targetPrimeFrames + LATENCY_CATCHUP_MARGIN) {
                while (state.frames.size > state.targetPrimeFrames) state.frames.pollFirstEntry()
                state.expectedSequence = state.frames.firstKey()
                state.consecutivePlc = 0
            }
        }
    }

    private fun playbackLoop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_AUDIO)
        var nextTickNs = System.nanoTime()

        while (playbackRunning.get()) {
            try {
                if (focusPaused.get()) {
                    Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                    nextTickNs = System.nanoTime()
                    continue
                }

                val nowNs = System.nanoTime()
                if (nowNs < nextTickNs) {
                    sleepNanos(nextTickNs - nowNs)
                } else if (nowNs - nextTickNs > FRAME_NS * 3) {
                    // Do not attempt to replay missed scheduler time after a stall.
                    nextTickNs = nowNs
                }
                nextTickNs += FRAME_NS

                val nowMs = System.currentTimeMillis()
                val frames = ArrayList<ByteArray>(sourceStates.size)
                var activeSource = false

                for ((sourceId, state) in sourceStates) {
                    val frame = synchronized(state) { pullPlayoutFrame(state, nowMs) }
                    if (frame != null) frames.add(frame)
                    if (nowMs - state.lastSeenMs <= SOURCE_SILENCE_HOLD_MS) activeSource = true

                    if (nowMs - state.lastSeenMs > SOURCE_EXPIRE_MS && synchronized(state) { state.frames.isEmpty() }) {
                        sourceStates.remove(sourceId, state)
                    }
                }

                if (frames.isEmpty() && !activeSource) {
                    Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                    nextTickNs = System.nanoTime() + FRAME_NS
                    continue
                }

                // Keep the AudioTrack clock moving at a fixed 20 ms cadence between voice packets.
                val mixed = if (frames.isEmpty()) SILENCE_FRAME else mixFrames(frames)
                val track = ensureTrack() ?: continue
                playbackActiveUntilMs = nowMs + ECHO_GUARD_AFTER_PLAYBACK_MS
                track.write(mixed, 0, mixed.size, AudioTrack.WRITE_BLOCKING)
            } catch (_: InterruptedException) {
                break
            } catch (_: Throwable) {
                Thread.sleep(PLAYBACK_IDLE_SLEEP_MS)
                nextTickNs = System.nanoTime() + FRAME_NS
            }
        }
    }

    private fun pullPlayoutFrame(state: SourceState, nowMs: Long): ByteArray? {
        while (state.frames.isNotEmpty()) {
            val expected = state.expectedSequence ?: break
            if (state.frames.firstKey() < expected) state.frames.pollFirstEntry() else break
        }

        if (!state.primed) {
            if (state.frames.size < state.targetPrimeFrames) return null
            state.expectedSequence = state.frames.firstKey()
            state.primed = true
        }

        var expected = state.expectedSequence ?: return null
        val exact = state.frames.remove(expected)
        if (exact != null) {
            state.expectedSequence = expected + 1
            state.lastGoodFrame = exact.audio
            state.consecutivePlc = 0
            return exact.audio
        }

        if (state.frames.isNotEmpty()) {
            val next = state.frames.firstKey()
            val gap = next - expected
            if (gap > 0 && gap <= MAX_PLC_GAP_FRAMES && state.consecutivePlc < MAX_PLC_GAP_FRAMES) {
                state.expectedSequence = expected + 1
                state.consecutivePlc++
                return concealFrame(state.lastGoodFrame, state.consecutivePlc)
            }

            // Large gap or sequence reset: resync immediately to the freshest available packet.
            if (gap > MAX_PLC_GAP_FRAMES || gap < -OLD_PACKET_TOLERANCE) {
                state.expectedSequence = next
                state.consecutivePlc = 0
                expected = next
                val fresh = state.frames.remove(expected)
                if (fresh != null) {
                    state.expectedSequence = expected + 1
                    state.lastGoodFrame = fresh.audio
                    return fresh.audio
                }
            }
        }

        // One very short concealment frame is allowed while waiting for a genuinely late packet.
        if (nowMs - state.lastSeenMs <= LATE_PACKET_GRACE_MS && state.consecutivePlc < 1) {
            state.expectedSequence = expected + 1
            state.consecutivePlc++
            return concealFrame(state.lastGoodFrame, state.consecutivePlc)
        }
        return null
    }

    private fun concealFrame(previous: ByteArray?, lossIndex: Int): ByteArray? {
        previous ?: return null
        val gain = if (lossIndex <= 1) 0.62 else 0.38
        val out = previous.copyOf()
        var i = 0
        while (i + 1 < out.size) {
            val lo = out[i].toInt() and 0xff
            val hi = out[i + 1].toInt()
            val sample = ((hi shl 8) or lo).toShort().toInt()
            val faded = (sample * gain).toInt().coerceIn(Short.MIN_VALUE.toInt(), Short.MAX_VALUE.toInt())
            out[i] = (faded and 0xff).toByte()
            out[i + 1] = ((faded shr 8) and 0xff).toByte()
            i += 2
        }
        return out
    }

    private fun targetPrimeFrames(jitterMs: Double): Int = when {
        jitterMs < 7.0 -> 2
        jitterMs < 15.0 -> 3
        jitterMs < 28.0 -> 4
        jitterMs < 45.0 -> 5
        else -> 6
    }

    private fun sleepNanos(nanos: Long) {
        if (nanos <= 0L) return
        val millis = nanos / 1_000_000L
        val extraNanos = (nanos % 1_000_000L).toInt()
        Thread.sleep(millis, extraNanos)
    }

'''
s = s[:start] + new_playback + s[end:]

old_release = '''        sourceQueues.clear()
        sourcePrimed.clear()
        sourceLastSeenMs.clear()
'''
s = replace_once(s, old_release, '        sourceStates.clear()\n', 'release source states')

old_constants = '''        private const val SOURCE_QUEUE_MAX_FRAMES = 3 // ~60 ms maximum per remote rider
        private const val SOURCE_PRIME_FRAMES = 2     // ~40 ms jitter buffer
        private const val SOURCE_EXPIRE_MS = 2_000L
        private const val PLAYBACK_IDLE_SLEEP_MS = 4L
        private const val ECHO_GUARD_AFTER_PLAYBACK_MS = 100L
'''
new_constants = '''        private const val MIN_PRIME_FRAMES = 2          // 40 ms on a clean link
        private const val MAX_SOURCE_QUEUE_FRAMES = 8   // hard cap: 160 ms
        private const val LATENCY_CATCHUP_MARGIN = 2
        private const val MAX_PLC_GAP_FRAMES = 2        // conceal at most 40 ms
        private const val OLD_PACKET_TOLERANCE = 32
        private const val SOURCE_EXPIRE_MS = 2_000L
        private const val SOURCE_SILENCE_HOLD_MS = 320L
        private const val LATE_PACKET_GRACE_MS = 45L
        private const val PLAYBACK_IDLE_SLEEP_MS = 3L
        private const val ECHO_GUARD_AFTER_PLAYBACK_MS = 100L
        private const val FRAME_NS = FRAME_MS * 1_000_000L
        private val SILENCE_FRAME = ByteArray(FRAME_BYTES)
'''
s = replace_once(s, old_constants, new_constants, 'audio constants')
p.write_text(s)

# -----------------------------------------------------------------------------
# Internet transport: pass sequence/timestamp to the audio engine and disable
# Nagle on the TLS socket to reduce small-packet delay.
# -----------------------------------------------------------------------------
p = root / 'app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt'
s = p.read_text()
s = replace_once(
    s,
    '        fun onInternetAudio(sourceId: String, audio: ByteArray)\n',
    '        fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray)\n',
    'Internet listener metadata',
)
s = replace_once(
    s,
    '                listener.onInternetAudio(packet.origin.toString(), packet.audio)\n',
    '                listener.onInternetAudio(packet.origin.toString(), packet.sequence, packet.timestampMs, packet.audio)\n',
    'Internet callback metadata',
)
s = replace_once(
    s,
    '''        val tls = (SSLSocketFactory.getDefault()
            .createSocket(PUBLIC_BROKER, PUBLIC_BROKER_TLS_PORT) as SSLSocket).apply {
            soTimeout = SOCKET_TIMEOUT_MS
            startHandshake()
        }
''',
    '''        val tls = (SSLSocketFactory.getDefault()
            .createSocket(PUBLIC_BROKER, PUBLIC_BROKER_TLS_PORT) as SSLSocket).apply {
            soTimeout = SOCKET_TIMEOUT_MS
            tcpNoDelay = true
            startHandshake()
        }
''',
    'TCP no delay',
)
p.write_text(s)

# -----------------------------------------------------------------------------
# Local mesh also already carries sequence and timestamp; expose them to playout.
# -----------------------------------------------------------------------------
p = root / 'app/src/main/java/com/bikemesh/ridemesh/mesh/MeshNode.kt'
s = p.read_text()
s = replace_once(
    s,
    '        fun onAudioPacket(sourceId: String, audio: ByteArray)\n',
    '        fun onAudioPacket(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray)\n',
    'Mesh listener metadata',
)
s = replace_once(
    s,
    '                    listener.onAudioPacket(packet.origin.toString(), packet.audio)\n',
    '                    listener.onAudioPacket(packet.origin.toString(), packet.sequence, packet.timestampMs, packet.audio)\n',
    'Mesh callback metadata',
)
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity wiring.
# -----------------------------------------------------------------------------
p = root / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()
s = replace_once(
    s,
    '''    override fun onAudioPacket(sourceId: String, audio: ByteArray) {
        if (!rideStarted) return
        val tileKey = meshNode.endpointIdForSource(sourceId) ?: sourceId
        markRiderSpeaking(tileKey)
        audioEngine.playIncoming(sourceId, audio)
    }
''',
    '''    override fun onAudioPacket(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {
        if (!rideStarted) return
        val tileKey = meshNode.endpointIdForSource(sourceId) ?: sourceId
        markRiderSpeaking(tileKey)
        audioEngine.playIncoming(sourceId, sequence, timestampMs, audio)
    }
''',
    'MainActivity mesh callback',
)
s = replace_once(
    s,
    '''    override fun onInternetAudio(sourceId: String, audio: ByteArray) {
        if (!rideStarted) return
        markRiderSpeaking(sourceId)
        audioEngine.playIncoming(sourceId, audio)
    }
''',
    '''    override fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {
        if (!rideStarted) return
        markRiderSpeaking(sourceId)
        audioEngine.playIncoming(sourceId, sequence, timestampMs, audio)
    }
''',
    'MainActivity Internet callback',
)
p.write_text(s)

print('RideMesh Beta3 low-latency audio patch applied.')
