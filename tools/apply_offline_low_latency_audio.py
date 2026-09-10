#!/usr/bin/env python3
from pathlib import Path
import re

p = Path("app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt")
s = p.read_text()

# Offline intercom policy: freshness beats continuity. Make this patch idempotent and
# resilient to comment/spacing differences so it works both in CI and local Android Studio.

def replace_const(name: str, value: str, comment: str | None = None):
    global s
    pattern = rf"(?m)^\s*private const val {re.escape(name)}\s*=\s*[^\n]+$"
    replacement = f"        private const val {name} = {value}"
    if comment:
        replacement += f"   // {comment}"
    if not re.search(pattern, s):
        raise SystemExit(f"Low-latency constant not found: {name}")
    s = re.sub(pattern, replacement, s, count=1)

replace_const("MIN_PRIME_FRAMES", "1", "20 ms: offline intercom starts immediately")
replace_const("MAX_SOURCE_QUEUE_FRAMES", "4", "hard cap: 80 ms; stale speech is discarded")
replace_const("LATENCY_CATCHUP_MARGIN", "1")
replace_const("MAX_PLC_GAP_FRAMES", "1", "conceal at most 20 ms")
replace_const("LATE_PACKET_GRACE_MS", "24L")
replace_const("VAD_PREROLL_FRAMES", "1")

# Replace the adaptive prime policy regardless of the previous threshold values.
target_pattern = re.compile(
    r"    private fun targetPrimeFrames\(jitterMs: Double\): Int = when \{\n"
    r"(?:        .*\n)+?"
    r"    \}\n",
    re.MULTILINE,
)
new_target = '''    private fun targetPrimeFrames(jitterMs: Double): Int = when {
        jitterMs < 12.0 -> 1
        jitterMs < 30.0 -> 2
        else -> 3
    }
'''
if not target_pattern.search(s):
    raise SystemExit("Low-latency targetPrimeFrames function not found")
s = target_pattern.sub(new_target, s, count=1)

# Insert burst freshness resync only once.
if "FRESHNESS_RESYNC_FRAMES" not in s:
    queue_anchor = '''            while (state.frames.size > MAX_SOURCE_QUEUE_FRAMES) {
                state.frames.pollFirstEntry()
            }
'''
    if queue_anchor not in s:
        raise SystemExit("Low-latency queue anchor missing")
    queue_insert = queue_anchor + '''            if (state.frames.size >= FRESHNESS_RESYNC_FRAMES) {
                while (state.frames.size > FRESHNESS_KEEP_FRAMES) state.frames.pollFirstEntry()
                state.expectedSequence = state.frames.firstKey()
                state.primed = true
                state.consecutivePlc = 0
            }
'''
    s = s.replace(queue_anchor, queue_insert, 1)

    const_anchor = "        private const val LATENCY_CATCHUP_MARGIN = 1\n"
    if const_anchor not in s:
        raise SystemExit("Low-latency constants anchor missing")
    s = s.replace(
        const_anchor,
        const_anchor
        + "        private const val FRESHNESS_RESYNC_FRAMES = 4\n"
        + "        private const val FRESHNESS_KEEP_FRAMES = 2\n",
        1,
    )

p.write_text(s)

# Nearby BYTES optimization: do not wait for remote transfer SUCCESS before allowing
# the next 20 ms voice frame. That serialized audio at transfer-completion latency and
# produced slow/choppy speech. Gate only until sendPayload() is accepted locally, while
# retaining newest-frame-wins if Android/Play Services is briefly busy.
np = Path("app/src/main/java/com/bikemesh/ridemesh/offline/NearbyClusterTransport.kt")
ns = np.read_text()

old_callback = '''        override fun onPayloadTransferUpdate(endpointId: String, update: PayloadTransferUpdate) {
            val current = audioInFlightPayload[endpointId] ?: return
            if (current != update.payloadId) return

            when (update.status) {
                PayloadTransferUpdate.Status.SUCCESS,
                PayloadTransferUpdate.Status.FAILURE,
                PayloadTransferUpdate.Status.CANCELED -> {
                    audioInFlightPayload.remove(endpointId, current)
                    val newest = audioLatestPending.remove(endpointId)
                    if (started && connectedEndpoints.contains(endpointId) && newest != null) {
                        sendRealtimeAudio(endpointId, newest)
                    }
                }
            }
        }
'''
if old_callback in ns:
    ns = ns.replace(old_callback, '', 1)

old_send = '''        client.sendPayload(endpointId, payload)
            .addOnFailureListener {
                audioInFlightPayload.remove(endpointId, payload.id)
                val newest = audioLatestPending.remove(endpointId)
                if (newest != null && started && connectedEndpoints.contains(endpointId)) {
                    sendRealtimeAudio(endpointId, newest)
                }
            }
'''
new_send = '''        client.sendPayload(endpointId, payload)
            .addOnCompleteListener {
                audioInFlightPayload.remove(endpointId, payload.id)
                val newest = audioLatestPending.remove(endpointId)
                if (newest != null && started && connectedEndpoints.contains(endpointId)) {
                    sendRealtimeAudio(endpointId, newest)
                }
            }
'''
if old_send in ns:
    ns = ns.replace(old_send, new_send, 1)
elif new_send not in ns:
    raise SystemExit("Nearby low-latency send anchor missing")

# Remove now-unused transfer-update import after switching to local enqueue completion.
ns = ns.replace('import com.google.android.gms.nearby.connection.PayloadTransferUpdate\n', '')
np.write_text(ns)

print("Applied offline low-latency audio policy: 20ms prime, <=80ms queue, burst resync, 20ms PLC")
print("Applied Nearby realtime voice policy: local-enqueue gate, newest-frame-wins, no transfer-completion serialization")
