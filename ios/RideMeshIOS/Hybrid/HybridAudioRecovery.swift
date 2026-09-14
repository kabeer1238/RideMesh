/// Retry budget is replenished only by real microphone callbacks, not engine.start().
/// A failed/stalled voice-processing unit falls back to regular input/output for
/// the rest of the ride. An explicit new ride starts with echo cancellation again.
struct HybridAudioRecovery {
    private(set) var attempts = 0
    private(set) var useVoiceProcessing = true
    var canRetry: Bool { attempts < 4 }
    mutating func beginAttempt() -> Bool {
        guard canRetry else { return false }
        attempts += 1
        return true
    }
    mutating func failedOrStalled() { useVoiceProcessing = false }
    mutating func capturedAudio() { attempts = 0 }
}
