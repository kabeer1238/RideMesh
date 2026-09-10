#!/usr/bin/env python3
from pathlib import Path

p = Path("app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt")
s = p.read_text()

# Offline intercom policy: freshness beats continuity. Nearby can deliver frames in
# bursts, so cap receiver history tightly and jump forward before old speech plays.
replacements = {
    "private const val MIN_PRIME_FRAMES = 2          // 40 ms on a clean link": "private const val MIN_PRIME_FRAMES = 1          // 20 ms: offline intercom starts immediately",
    "private const val MAX_SOURCE_QUEUE_FRAMES = 8   // hard cap: 160 ms": "private const val MAX_SOURCE_QUEUE_FRAMES = 4   // hard cap: 80 ms; stale speech is discarded",
    "private const val LATENCY_CATCHUP_MARGIN = 2": "private const val LATENCY_CATCHUP_MARGIN = 1",
    "private const val MAX_PLC_GAP_FRAMES = 2        // conceal at most 40 ms": "private const val MAX_PLC_GAP_FRAMES = 1        // conceal at most 20 ms",
    "private const val LATE_PACKET_GRACE_MS = 45L": "private const val LATE_PACKET_GRACE_MS = 24L",
    "private const val VAD_PREROLL_FRAMES = 2": "private const val VAD_PREROLL_FRAMES = 1",
}
for old, new in replacements.items():
    if old not in s:
        raise SystemExit(f"Low-latency patch anchor missing: {old}")
    s = s.replace(old, new, 1)

old_target = '''    private fun targetPrimeFrames(jitterMs: Double): Int = when {
        jitterMs < 7.0 -> 2
        jitterMs < 15.0 -> 3
        jitterMs < 28.0 -> 4
        jitterMs < 45.0 -> 5
        else -> 6
    }
'''
new_target = '''    private fun targetPrimeFrames(jitterMs: Double): Int = when {
        jitterMs < 12.0 -> 1
        jitterMs < 30.0 -> 2
        else -> 3
    }
'''
if old_target not in s:
    raise SystemExit("Low-latency targetPrimeFrames anchor missing")
s = s.replace(old_target, new_target, 1)

# If a Nearby burst arrives, retain only the freshest ~60 ms before playout.
old_queue = '''            while (state.frames.size > MAX_SOURCE_QUEUE_FRAMES) {
                state.frames.pollFirstEntry()
            }

            // If the receiver ever gets far behind, jump forward rather than playing old speech.
'''
new_queue = '''            while (state.frames.size > MAX_SOURCE_QUEUE_FRAMES) {
                state.frames.pollFirstEntry()
            }
            if (state.frames.size >= FRESHNESS_RESYNC_FRAMES) {
                while (state.frames.size > FRESHNESS_KEEP_FRAMES) state.frames.pollFirstEntry()
                state.expectedSequence = state.frames.firstKey()
                state.primed = true
                state.consecutivePlc = 0
            }

            // If the receiver ever gets far behind, jump forward rather than playing old speech.
'''
if old_queue not in s:
    raise SystemExit("Low-latency queue anchor missing")
s = s.replace(old_queue, new_queue, 1)

const_anchor = "        private const val LATENCY_CATCHUP_MARGIN = 1\n"
if const_anchor not in s:
    raise SystemExit("Low-latency constants anchor missing")
s = s.replace(const_anchor, const_anchor + "        private const val FRESHNESS_RESYNC_FRAMES = 4\n        private const val FRESHNESS_KEEP_FRAMES = 2\n", 1)

p.write_text(s)
print("Applied offline low-latency audio policy: 20ms prime, <=80ms queue, burst resync, 20ms PLC")
