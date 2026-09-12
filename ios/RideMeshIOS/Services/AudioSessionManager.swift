import AVFoundation
import Foundation
import WebRTC

@MainActor
final class AudioSessionManager: ObservableObject {
    @Published private(set) var routeText = "Audio ready"
    @Published private(set) var helmetAvailable = false
    @Published private(set) var isInterrupted = false
    @Published private(set) var isRemoteSpeechDucking = false

    private let session = AVAudioSession.sharedInstance()
    private var notificationTokens: [NSObjectProtocol] = []
    private var selectedRoute: RideAudioRoute = .automatic
    private var rideConfigured = false
    private var duckReleaseTask: Task<Void, Never>?
    private var duckTransitionTask: Task<Void, Never>?
    private var recoveryTask: Task<Void, Never>?
    private var routeRecoveryTask: Task<Void, Never>?
    private var externalAudioWasPlayingBeforeDuck = false

    init() {
        observeAudioSession()
        refreshRouteState()
    }

    deinit {
        duckReleaseTask?.cancel()
        duckTransitionTask?.cancel()
        recoveryTask?.cancel()
        routeRecoveryTask?.cancel()
        notificationTokens.forEach(NotificationCenter.default.removeObserver)
    }

    func requestMicrophonePermission() async -> Bool {
        if #available(iOS 17.0, *) {
            return await AVAudioApplication.requestRecordPermission()
        }

        return await withCheckedContinuation { continuation in
            session.requestRecordPermission { allowed in
                continuation.resume(returning: allowed)
            }
        }
    }

    func configureForRide(route: RideAudioRoute) throws {
        selectedRoute = route
        rideConfigured = true
        isRemoteSpeechDucking = false
        externalAudioWasPlayingBeforeDuck = false

#if targetEnvironment(simulator)
        routeText = "Simulator audio • device test required"
        helmetAvailable = false
        return
#else
        // One component owns the app audio session. WebRTC is given the same base
        // configuration, but Smart Ducking no longer asks WebRTC to reconfigure the
        // session every time speech starts/stops. This avoids media interruption and
        // Bluetooth route churn on iOS 26.
        installWebRTCBaseConfiguration(duckOthers: false)
        try applyRideCategory(duckOthers: false)
        try session.setPreferredSampleRate(48_000)
        try session.setPreferredIOBufferDuration(0.01)
        try session.setActive(true)
        try applyRoute(route, allowFallback: false)
        refreshRouteState()
#endif
    }

    func deactivate() {
        duckReleaseTask?.cancel()
        duckReleaseTask = nil
        duckTransitionTask?.cancel()
        duckTransitionTask = nil
        recoveryTask?.cancel()
        recoveryTask = nil
        routeRecoveryTask?.cancel()
        routeRecoveryTask = nil
        isRemoteSpeechDucking = false
        externalAudioWasPlayingBeforeDuck = false
        rideConfigured = false

#if targetEnvironment(simulator)
        routeText = "Simulator audio • device test required"
#else
        // notifyOthersOnDeactivation is essential for media apps that were ever
        // interrupted while RideMesh was active.
        try? session.setActive(false, options: [.notifyOthersOnDeactivation])
        refreshRouteState()
#endif
    }

    func select(route: RideAudioRoute) throws {
        selectedRoute = route
#if targetEnvironment(simulator)
        routeText = "Simulator audio • device test required"
        helmetAvailable = false
        return
#else
        try applyRoute(route, allowFallback: false)
        refreshRouteState()
#endif
    }

    /// RideMesh never captures another app's playback. WebRTC receives only the
    /// microphone track. Smart Ducking uses Apple's audio-session ducking instead
    /// of directly changing another app's volume.
    ///
    /// iOS does not expose an API to set Spotify/Apple Music to an exact percentage,
    /// so the perceived attenuation is system controlled. The transition here is
    /// deliberately session-safe: speech enables temporary `.duckOthers`; release
    /// explicitly notifies other audio sessions before returning to mix-only mode.
    func setSpeechDuckingActive(_ active: Bool) {
        guard rideConfigured, !isInterrupted else { return }
#if targetEnvironment(simulator)
        isRemoteSpeechDucking = active
        return
#else
        duckReleaseTask?.cancel()
        duckReleaseTask = nil

        if active {
            guard !isRemoteSpeechDucking else { return }
            externalAudioWasPlayingBeforeDuck = session.isOtherAudioPlaying
            transitionDucking(to: true)
            return
        }

        // 0.9 s speech hangover keeps music lowered naturally between words and
        // sentences. We never store/force the user's media volume.
        duckReleaseTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(900))
            guard !Task.isCancelled,
                  let self,
                  self.rideConfigured,
                  !self.isInterrupted else { return }
            self.transitionDucking(to: false)
        }
#endif
    }

    /// Re-asserts the long-lived RideMesh voice session after another app temporarily
    /// owns the microphone (phone/FaceTime/WhatsApp voice recording, etc.).
    ///
    /// Important: the active ride itself is never torn down. We retry activation for a
    /// short window because some apps release the microphone a fraction of a second
    /// after their interruption notification. `isInterrupted` is cleared only after
    /// AVAudioSession is ours again, which lets WebRTC restart capture at the right time.
    func resumeAfterInterruption() {
        guard rideConfigured else { return }
#if targetEnvironment(simulator)
        routeText = "Simulator audio • device test required"
        isRemoteSpeechDucking = false
        isInterrupted = false
#else
        scheduleAudioRecovery(reason: "Audio resumed")
#endif
    }

    /// Foreground safety net. Apple notes that an interruption-began notification is not
    /// guaranteed to have a matching ended notification. When the rider returns to
    /// RideMesh, reassert the voice session without requiring END RIDE / restart.
    func ensureRideAudioActive() {
        guard rideConfigured else { return }
#if targetEnvironment(simulator)
        routeText = "Simulator audio • device test required"
#else
        scheduleAudioRecovery(reason: "Voice ready")
#endif
    }

#if !targetEnvironment(simulator)
    private func scheduleAudioRecovery(reason: String) {
        recoveryTask?.cancel()
        recoveryTask = Task { @MainActor [weak self] in
            guard let self else { return }

            // Fast first retry, then two gentle retries. This covers WhatsApp/VoIP
            // microphone release timing without hammering the audio server.
            let delays: [Duration] = [.milliseconds(120), .milliseconds(320), .milliseconds(700)]
            var lastError: Error?

            for delay in delays {
                try? await Task.sleep(for: delay)
                guard !Task.isCancelled, self.rideConfigured else { return }
                do {
                    self.duckReleaseTask?.cancel()
                    self.duckReleaseTask = nil
                    self.duckTransitionTask?.cancel()
                    self.duckTransitionTask = nil
                    self.isRemoteSpeechDucking = false
                    self.externalAudioWasPlayingBeforeDuck = false

                    self.installWebRTCBaseConfiguration(duckOthers: false)
                    try self.applyRideCategory(duckOthers: false)
                    try self.session.setActive(true)
                    try self.applyRoute(self.selectedRoute, allowFallback: true)
                    self.refreshRouteState()
                    self.routeText = self.routeText.isEmpty ? reason : self.routeText

                    // Clearing this publishes the recovery to WebRTCVoiceService, which
                    // then restarts its manual audio unit and re-enables the mic track.
                    self.isInterrupted = false
                    return
                } catch {
                    lastError = error
                }
            }

            if let lastError {
                self.routeText = "Audio reconnecting… • \(lastError.localizedDescription)"
            } else {
                self.routeText = "Audio reconnecting…"
            }
        }
    }

    /// Smart Ducking MUST NOT deactivate AVAudioSession. Deactivation was the cause of
    /// two real-device failures in vc18: the WebRTC microphone could disappear while
    /// music was playing, and could remain stopped after WhatsApp voice recording.
    ///
    /// iOS permits changing category/options while active (with an immediate route
    /// reevaluation). We keep the session continuously active and only change the
    /// temporary ducking option. This preserves WebRTC capture and background voice.
    private func transitionDucking(to enabled: Bool) {
        duckTransitionTask?.cancel()
        duckTransitionTask = Task { @MainActor [weak self] in
            guard let self, self.rideConfigured, !self.isInterrupted else { return }
            do {
                self.installWebRTCBaseConfiguration(duckOthers: enabled)
                try self.applyRideCategory(duckOthers: enabled)

                // Reasserting TRUE is safe; importantly, there is no FALSE transition.
                // This asks iOS to apply the new mix/duck policy without surrendering
                // the microphone or stopping WebRTC's voice-processing I/O unit.
                try self.session.setActive(true)
                try self.applyRoute(self.selectedRoute, allowFallback: true)

                self.isRemoteSpeechDucking = enabled
                if !enabled { self.externalAudioWasPlayingBeforeDuck = false }
                self.refreshRouteState()
            } catch {
                self.isRemoteSpeechDucking = false
                if !enabled { self.externalAudioWasPlayingBeforeDuck = false }

                // Voice always wins over cosmetic ducking. Fall back to stable mixing
                // without ever deactivating the active ride audio session.
                self.installWebRTCBaseConfiguration(duckOthers: false)
                try? self.applyRideCategory(duckOthers: false)
                try? self.session.setActive(true)
                try? self.applyRoute(self.selectedRoute, allowFallback: true)
                self.routeText = "Voice ready • music control recovering"
            }
        }
    }

    private func baseCategoryOptions() -> AVAudioSession.CategoryOptions {
        var options: AVAudioSession.CategoryOptions = [
            .defaultToSpeaker,
            .allowBluetoothA2DP,
            .mixWithOthers
        ]

        if #available(iOS 26.0, *) {
            options.insert(.allowBluetoothHFP)
        } else {
            options.insert(.allowBluetooth)
        }
        return options
    }

    private func applyRideCategory(duckOthers: Bool) throws {
        var options = baseCategoryOptions()
        if duckOthers {
            options.insert(.duckOthers)
        }

        try session.setCategory(.playAndRecord, mode: .voiceChat, options: options)
    }

    private func installWebRTCBaseConfiguration(duckOthers: Bool) {
        var options = baseCategoryOptions()
        if duckOthers {
            options.insert(.duckOthers)
        }

        let webRTCConfig = RTCAudioSessionConfiguration()
        webRTCConfig.category = AVAudioSession.Category.playAndRecord.rawValue
        webRTCConfig.mode = AVAudioSession.Mode.voiceChat.rawValue
        webRTCConfig.categoryOptions = options
        webRTCConfig.sampleRate = 48_000
        webRTCConfig.ioBufferDuration = 0.01
        RTCAudioSessionConfiguration.setWebRTC(webRTCConfig)
    }

    private func applyRoute(_ route: RideAudioRoute, allowFallback: Bool) throws {
        switch route {
        case .phone:
            try session.setPreferredInput(nil)
            try session.overrideOutputAudioPort(.speaker)

        case .helmet:
            guard let input = session.availableInputs?.first(where: {
                $0.portType == .bluetoothHFP || $0.portType == .headsetMic
            }) else {
                if allowFallback {
                    try session.setPreferredInput(nil)
                    try session.overrideOutputAudioPort(.speaker)
                    routeText = "Helmet unavailable • phone audio restored"
                    return
                }
                throw AudioRouteError.helmetUnavailable
            }
            try session.overrideOutputAudioPort(.none)
            try session.setPreferredInput(input)

        case .automatic:
            if let helmet = session.availableInputs?.first(where: { $0.portType == .bluetoothHFP }) {
                try session.overrideOutputAudioPort(.none)
                try session.setPreferredInput(helmet)
            } else {
                try session.setPreferredInput(nil)
                try session.overrideOutputAudioPort(.speaker)
            }
        }
    }
#endif

    private func observeAudioSession() {
        let center = NotificationCenter.default
        notificationTokens.append(
            center.addObserver(forName: AVAudioSession.routeChangeNotification, object: session, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    guard let self else { return }
                    self.refreshRouteState()
#if !targetEnvironment(simulator)
                    // Route self-healing: whether the rider chose AUTO or explicitly
                    // selected HELMET, fall back safely when HFP disappears and move
                    // back to the requested helmet route when it returns. A short
                    // debounce lets iOS finish publishing its new availableInputs.
                    if self.rideConfigured, !self.isInterrupted {
                        self.routeRecoveryTask?.cancel()
                        self.routeRecoveryTask = Task { @MainActor [weak self] in
                            try? await Task.sleep(for: .milliseconds(240))
                            guard let self, self.rideConfigured, !self.isInterrupted else { return }
                            try? self.applyRoute(self.selectedRoute, allowFallback: true)
                            self.refreshRouteState()
                        }
                    }
#endif
                }
            }
        )
        notificationTokens.append(
            center.addObserver(forName: AVAudioSession.interruptionNotification, object: session, queue: .main) { [weak self] note in
                Task { @MainActor in self?.handleInterruption(note) }
            }
        )
        notificationTokens.append(
            center.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification, object: session, queue: .main) { [weak self] _ in
                Task { @MainActor in
                    guard let self else { return }
                    if self.rideConfigured {
                        self.resumeAfterInterruption()
                    } else {
                        self.refreshRouteState()
                    }
                }
            }
        )
    }

    private func handleInterruption(_ notification: Notification) {
        guard let raw = notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt,
              let type = AVAudioSession.InterruptionType(rawValue: raw) else { return }

        switch type {
        case .began:
            duckReleaseTask?.cancel()
            duckReleaseTask = nil
            duckTransitionTask?.cancel()
            duckTransitionTask = nil
            isRemoteSpeechDucking = false
            externalAudioWasPlayingBeforeDuck = false
            isInterrupted = true
            routeText = "CALL / OTHER AUDIO ACTIVE • RIDEMESH PAUSED"

        case .ended:
            routeText = "RESUMING RIDEMESH…"
            // Keep isInterrupted=true until AVAudioSession has genuinely been
            // reacquired. This prevents WebRTC from restarting its microphone too early.
            resumeAfterInterruption()

        @unknown default:
            break
        }
    }

    func refreshRouteState() {
#if targetEnvironment(simulator)
        helmetAvailable = false
        if rideConfigured { routeText = "Simulator audio • device test required" }
#else
        let current = session.currentRoute
        helmetAvailable = (session.availableInputs ?? []).contains { $0.portType == .bluetoothHFP }
        let outputs = current.outputs.map(\.portName)
        let inputs = current.inputs.map(\.portName)
        let combined = (outputs + inputs).uniqued()
        if combined.isEmpty {
            routeText = "Audio ready"
        } else if isRemoteSpeechDucking {
            routeText = combined.joined(separator: " • ") + " • MUSIC LOWERED"
        } else {
            routeText = combined.joined(separator: " • ")
        }
#endif
    }
}

enum AudioRouteError: LocalizedError {
    case helmetUnavailable

    var errorDescription: String? {
        switch self {
        case .helmetUnavailable:
            return "No Bluetooth HFP helmet/headset is currently available."
        }
    }
}

private extension Array where Element: Hashable {
    func uniqued() -> [Element] {
        var seen = Set<Element>()
        return filter { seen.insert($0).inserted }
    }
}
