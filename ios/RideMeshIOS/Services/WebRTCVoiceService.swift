import AVFoundation
import Foundation
import WebRTC

@MainActor
final class WebRTCVoiceService: NSObject, ObservableObject {
    @Published private(set) var statusText = "VOICE READY"
    @Published private(set) var peers: [RiderPeer] = []
    @Published private(set) var diagnostics = RideMeshDiagnostics()
    @Published private(set) var remoteSpeechActive = false
    @Published private(set) var localSpeechActive = false
    @Published private(set) var smartDuckingActive = false
    @Published private(set) var riderLocations: [UUID: RiderLocationPacket] = [:]

    private static let factory: RTCPeerConnectionFactory = {
        RTCInitializeSSL()
        return RTCPeerConnectionFactory(
            encoderFactory: RTCDefaultVideoEncoderFactory(),
            decoderFactory: RTCDefaultVideoDecoderFactory()
        )
    }()

    /// Lightweight speech gate built around WebRTC's own processed audio levels/VAD flag.
    /// It adapts to a sustained noise floor, rejects isolated spikes, and requires a
    /// short speech-like pattern before declaring speech when WebRTC does not expose
    /// an explicit voiceActivityFlag statistic.
    private struct AdaptiveSpeechGate {
        var noiseFloor: Double = 0.004
        var consecutiveSpeech = 0
        var consecutiveQuiet = 0
        var active = false
        var history: [Double] = []

        mutating func update(level rawLevel: Double?, explicitVoice: Bool?) -> Bool {
            let level = max(0, min(rawLevel ?? 0, 1))
            history.append(level)
            if history.count > 6 { history.removeFirst(history.count - 6) }

            let threshold = max(0.014, min(0.11, (noiseFloor * 3.0) + 0.004))

            let mean = history.isEmpty ? 0 : history.reduce(0, +) / Double(history.count)
            let variance = history.isEmpty ? 0 : history.reduce(0) { $0 + pow($1 - mean, 2) } / Double(history.count)
            let modulation = sqrt(variance)
            let peak = history.max() ?? 0
            let valley = history.min() ?? 0
            let dynamicRange = max(0, peak - valley)

            // Motorcycle wind/engine noise is often loud but comparatively steady.
            // Human speech is normally more modulated over a short window.  This
            // classifier is used ONLY for activity/ducking decisions; it never gates
            // or mutes the outgoing microphone track.
            let steadyNoise = history.count >= 4
                && modulation < max(0.0020, mean * 0.12)
                && dynamicRange < max(0.006, mean * 0.24)

            if !active {
                // Learn both quiet ambience and sustained wind/engine noise as the
                // current floor.  The cap prevents an extremely loud transient from
                // teaching the gate that all future speech is "background".
                if level <= threshold * 1.20 || steadyNoise {
                    let learnRate = steadyNoise ? 0.16 : 0.055
                    let sample = min(level, 0.085)
                    noiseFloor = max(0.0015, min(0.085, (noiseFloor * (1 - learnRate)) + (sample * learnRate)))
                }
            }

            let updatedThreshold = max(0.014, min(0.11, (noiseFloor * 3.0) + 0.004))
            let levelSpeechLike = history.count >= 3
                && level > updatedThreshold
                && !steadyNoise
                && modulation > max(0.0022, noiseFloor * 0.22)
                && dynamicRange > max(0.006, noiseFloor * 0.40)

            // Trust WebRTC VAD only when the short-term pattern is not clearly
            // steady-noise dominated.  At a high learned noise floor we require a
            // second confirming sample so helmet wind does not continuously duck.
            let explicitLooksSafe = explicitVoice == true && !steadyNoise
            let candidate = explicitLooksSafe || levelSpeechLike

            if candidate {
                consecutiveSpeech += 1
                consecutiveQuiet = 0
            } else {
                consecutiveQuiet += 1
                consecutiveSpeech = 0
            }

            let noisyEnvironment = noiseFloor >= 0.022
            let confirmationFrames = noisyEnvironment ? 2 : (explicitLooksSafe ? 1 : 2)
            if !active, consecutiveSpeech >= confirmationFrames { active = true }
            if active, consecutiveQuiet >= 2 { active = false }
            return active
        }

        mutating func reset() {
            consecutiveSpeech = 0
            consecutiveQuiet = 0
            active = false
            history.removeAll(keepingCapacity: true)
        }
    }

    private final class PeerSession {
        let id: UUID
        let pc: RTCPeerConnection
        let initiator: Bool
        var pendingCandidates: [RTCIceCandidate] = []
        var seenCandidateKeys = Set<String>()
        var remoteDescriptionSet = false
        var connected = false
        var lastOfferAt = Date.distantPast
        var lastRecoveryAt = Date.distantPast
        var recoveryAttempts = 0
        var disconnectTask: Task<Void, Never>?
        var lastPacketsReceived: Double?
        var lastPacketsLost: Double?
        var lastQuality: RiderConnectionQuality = .reconnecting
        var qualityStreak = 0
        var lastAppliedBitrateBps: Int?
        var lastRTTMs: Double?
        var lastJitterMs: Double?
        var lastLossPercent: Double?
        var lastTotalAudioEnergy: Double?
        var lastTotalSamplesDuration: Double?
        var speechGate = AdaptiveSpeechGate()

        init(id: UUID, pc: RTCPeerConnection, initiator: Bool) {
            self.id = id
            self.pc = pc
            self.initiator = initiator
        }
    }

    private(set) var hybridMode = false
    private var hybridChannels: [UUID:RTCDataChannel] = [:]
    var onHybridPacket: ((UUID,Data) -> Void)?
    var hybridPeerIDs: Set<UUID> { Set(hybridChannels.filter { $0.value.readyState == .open }.keys) }
    func sendHybrid(_ peer: UUID, _ data: Data) {
        guard let channel = hybridChannels[peer], channel.readyState == .open,
              data.count <= 2048, channel.bufferedAmount + UInt64(data.count) <= 4096 else { return }
        _ = channel.sendData(RTCDataBuffer(data:data,isBinary:true))
    }
    private func registerHybrid(_ channel: RTCDataChannel, peer: UUID) {
        guard hybridMode, channel.label == "ridemesh-hybrid33", hybridChannels[peer] == nil else { channel.close(); return }
        hybridChannels[peer] = channel; channel.delegate = self
    }
    private let signaling = RideMeshSignalingService()
    private var sessions: [UUID: PeerSession] = [:]
    private var audioSource: RTCAudioSource?
    private var localAudioTrack: RTCAudioTrack?
    private let rtcAudioSession = RTCAudioSession.sharedInstance()
    private var audioRestartTask: Task<Void, Never>?
    private var userMuted = false
    private var systemInterrupted = false
    private var running = false
    private var offerRetryTimer: Timer?
    private var speechStatsTimer: Timer?
    private var qualityStatsTimer: Timer?
    private var speechStateByPeer: [UUID: Bool] = [:]
    private var localSpeechGate = AdaptiveSpeechGate()
    private var localLastTotalAudioEnergy: Double?
    private var localLastTotalSamplesDuration: Double?
    private var batterySmart = true
    private var otherAudioWasPlaying = false
    private var musicBaselineUntil = Date.distantPast
    private var speechStatsInterval: TimeInterval = 0.80

    override init() {
        super.init()
        signaling.onPeerSeen = { [weak self] peer in
            Task { @MainActor in
                guard let self else { return }
                self.peers = self.signaling.peers
                _ = self.ensurePeer(peer.id, allowOffer: true)
                self.refreshDiagnostics()
            }
        }
        signaling.onPeerExpired = { [weak self] id in
            Task { @MainActor in
                self?.closePeer(id)
                self?.peers = self?.signaling.peers ?? []
                self?.refreshDiagnostics()
            }
        }
        signaling.onSignal = { [weak self] signal in
            Task { @MainActor in self?.handleSignal(signal) }
        }
        signaling.onTransportRestored = { [weak self] in
            Task { @MainActor in self?.handleSignalingRestored() }
        }
        signaling.onLocation = { [weak self] packet in
            Task { @MainActor in
                guard let self else { return }
                var updated = packet
                if let peer = self.signaling.peers.first(where: { $0.id == packet.riderId }) {
                    updated.displayName = peer.displayName
                    updated.connectionQuality = peer.connected ? peer.connectionQuality : .reconnecting
                }
                self.riderLocations[packet.riderId] = updated
            }
        }
    }

    func start(rideCode: String, riderName: String, deviceName: String, batterySmart: Bool = true, hybrid: Bool = false) {
        stop()
        running = true
        hybridMode = hybrid
        self.batterySmart = batterySmart

        // Manual WebRTC audio is critical on iOS when another foreground app briefly
        // takes the microphone. RideMesh keeps the peer/session alive and explicitly
        // restarts WebRTC's voice-processing I/O after the interruption ends.
        rtcAudioSession.useManualAudio = true
        rtcAudioSession.isAudioEnabled = !hybridMode
        if !hybridMode { setupLocalAudioTrack() }

        signaling.start(rideCode: rideCode, riderName: riderName, deviceName: deviceName, batterySmart: batterySmart, hybrid:hybridMode)
        statusText = "CONNECTING…"
        startOfferRetryTimer()
        if !hybridMode { startSpeechStatsTimer() }
        startQualityStatsTimer()
    }

    func stop() {
        running = false
        hybridChannels.values.forEach { $0.delegate = nil; $0.close() }; hybridChannels.removeAll()
        audioRestartTask?.cancel()
        audioRestartTask = nil
        rtcAudioSession.isAudioEnabled = false
        signaling.stop()
        offerRetryTimer?.invalidate()
        offerRetryTimer = nil
        speechStatsTimer?.invalidate()
        speechStatsTimer = nil
        qualityStatsTimer?.invalidate()
        qualityStatsTimer = nil
        sessions.values.forEach {
            $0.disconnectTask?.cancel()
            $0.pc.close()
        }
        sessions.removeAll()
        speechStateByPeer.removeAll()
        localSpeechGate.reset()
        otherAudioWasPlaying = false
        musicBaselineUntil = .distantPast
        localLastTotalAudioEnergy = nil
        localLastTotalSamplesDuration = nil
        setRemoteSpeechState(false)
        setLocalSpeechState(false)
        localAudioTrack?.isEnabled = false
        localAudioTrack = nil
        audioSource = nil
        peers = []
        riderLocations.removeAll()
        statusText = "VOICE READY"
        refreshDiagnostics()
    }

    func setMuted(_ muted: Bool) {
        userMuted = muted
        if muted {
            localSpeechGate.reset()
            setLocalSpeechState(false)
        }
        applyVoiceEnabled()
    }

    var localRiderID: UUID { signaling.nodeID }

    func publishLocation(_ packet: RiderLocationPacket) {
        guard running else { return }
        signaling.publishLocation(packet)
    }

    func setSystemInterrupted(_ interrupted: Bool) {
        systemInterrupted = interrupted
        if interrupted {
            audioRestartTask?.cancel()
            audioRestartTask = nil
            // Stop WebRTC's audio unit while WhatsApp/phone/another app owns the mic,
            // but keep peer connections and signaling alive in the background.
            rtcAudioSession.isAudioEnabled = false
            localSpeechGate.reset()
            setRemoteSpeechState(false)
            setLocalSpeechState(false)
            applyVoiceEnabled()
            return
        }

        // AVAudioSession has already been reacquired by AudioSessionManager. Force a
        // clean WebRTC audio-unit restart; simply re-enabling the RTCAudioTrack was not
        // sufficient after WhatsApp voice recording on real iPhones.
        restartWebRTCAudioUnit()
        recoverConnectionsAfterInterruption()
        applyVoiceEnabled()
    }

    /// Foreground / route-change safety net. Does not renegotiate peers or leave the
    /// ride; it only ensures the WebRTC playout/recording unit and mic track are alive.
    func ensureAudioCaptureRunning() {
        guard running, !systemInterrupted else { return }
        restartWebRTCAudioUnit()
    }

    /// Preserve the active Ride Code/session across Wi-Fi <-> cellular handovers.
    /// Signaling is moved onto the new path immediately and existing peers are
    /// recovered in place; the rider never needs to rescan a QR or re-enter a code.
    func handleNetworkPathChange(isOnline: Bool, interface: String) {
        guard running else { return }
        if !isOnline {
            statusText = "RECONNECTING…"
            for session in sessions.values {
                signaling.updatePeerQuality(session.id, quality: .reconnecting)
            }
            peers = signaling.peers
            refreshDiagnostics()
            return
        }

        signaling.handleNetworkPathChange(isOnline: true)
        statusText = "RECONNECTING…"
        for session in Array(sessions.values) {
            session.lastRecoveryAt = .distantPast
            if session.initiator, session.pc.signalingState == .stable {
                diagnostics.connectionRecoveries += 1
                session.pc.restartIce()
                maybeCreateOffer(session, force: true)
            } else if session.pc.iceConnectionState == .failed || session.pc.iceConnectionState == .closed {
                rebuildPeer(session.id, reason: "network handover")
            }
        }
        refreshDiagnostics()
    }

    private func restartWebRTCAudioUnit() {
        guard !hybridMode else { return }
        guard running else { return }
        audioRestartTask?.cancel()
        rtcAudioSession.useManualAudio = true
        rtcAudioSession.isAudioEnabled = false

        audioRestartTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .milliseconds(90))
            guard let self, self.running, !self.systemInterrupted else { return }
            self.rtcAudioSession.isAudioEnabled = true
            self.localAudioTrack?.isEnabled = !self.userMuted
            self.applyVoiceEnabled()
        }
    }

    private func setupLocalAudioTrack() {
        // Cautious motorcycle voice-processing profile.  Keep WebRTC/iOS voice
        // processing continuously enabled rather than hard-muting on VAD.  Noise
        // suppression + high-pass filtering reduce steady road/wind/engine energy,
        // while voiceChat mode (owned by AudioSessionManager) keeps Apple's native
        // voice-processing path active.  VAD is deliberately NOT used as a transmit
        // gate, so the beginnings/endings of words are not clipped.
        let constraints = RTCMediaConstraints(
            mandatoryConstraints: nil,
            optionalConstraints: [
                "googEchoCancellation": "true",
                "googNoiseSuppression": "true",
                "googAutoGainControl": "true",
                "googHighpassFilter": "true"
            ]
        )
        let source = Self.factory.audioSource(with: constraints)
        audioSource = source
        localAudioTrack = Self.factory.audioTrack(with: source, trackId: "ridemesh-audio")
        applyVoiceEnabled()
    }

    private func applyVoiceEnabled() {
        localAudioTrack?.isEnabled = !userMuted && !systemInterrupted
        if userMuted {
            statusText = "MIC MUTED • LISTENING ONLY"
        } else if systemInterrupted {
            statusText = "CALL / OTHER AUDIO ACTIVE • RIDEMESH PAUSED"
        } else if sessions.values.contains(where: { $0.connected }) {
            statusText = smartDuckingActive ? "SPEECH ACTIVE • MUSIC LOWERED" : "VOICE READY"
        } else if signaling.connected {
            statusText = "VOICE READY"
        } else {
            statusText = "RECONNECTING…"
        }
    }

    @discardableResult
    private func ensurePeer(_ peerID: UUID, allowOffer: Bool) -> PeerSession? {
        if let existing = sessions[peerID] {
            if allowOffer, existing.initiator, !existing.connected {
                maybeCreateOffer(existing)
            }
            return existing
        }

        let config = RTCConfiguration()
        config.iceServers = [
            RTCIceServer(urlStrings: ["stun:stun.l.google.com:19302"]),
            RTCIceServer(urlStrings: ["stun:stun1.l.google.com:19302"])
        ]
        config.sdpSemantics = .unifiedPlan
        config.bundlePolicy = .maxBundle
        config.rtcpMuxPolicy = .require
        config.iceTransportPolicy = .all
        config.continualGatheringPolicy = .gatherContinually

        // vc20 Low-Latency Voice: WebRTC/NetEq defaults allow a receiver jitter
        // buffer of up to 50 packets. For RideMesh's 20 ms intercom packets that
        // ceiling can permit far more queued speech than a natural conversation
        // can tolerate after a period of network jitter. Cap it more aggressively
        // and let NetEq accelerate playout when it has accumulated excess delay.
        // This is intentionally a ceiling, not a fixed 400 ms target.
        config.audioJitterBufferMaxPackets = 20
        config.audioJitterBufferFastAccelerate = true

        // Permit WebRTC to mark real-time media with DSCP when the underlying
        // network honors it. This is a hint only and is safe to ignore by networks.
        config.enableDscp = true

        let constraints = RTCMediaConstraints(
            mandatoryConstraints: nil,
            optionalConstraints: ["DtlsSrtpKeyAgreement": "true"]
        )
        guard let pc = Self.factory.peerConnection(with: config, constraints: constraints, delegate: self) else {
            diagnostics.lastError = "Could not create WebRTC peer connection"
            return nil
        }

        if let track = localAudioTrack {
            pc.add(track, streamIds: ["ridemesh-stream"])
        }

        let initiator = signaling.nodeID.uuidString.lowercased() < peerID.uuidString.lowercased()
        let session = PeerSession(id: peerID, pc: pc, initiator: initiator)
        sessions[peerID] = session
        if hybridMode && initiator {
            let config = RTCDataChannelConfiguration(); config.isOrdered = false; config.maxRetransmits = 0
            if let channel = pc.dataChannel(forLabel:"ridemesh-hybrid33",configuration:config) { registerHybrid(channel,peer:peerID) }
        }
        speechStateByPeer[peerID] = false
        if allowOffer, initiator { maybeCreateOffer(session) }
        return session
    }

    private func maybeCreateOffer(_ session: PeerSession, force: Bool = false) {
        guard running, session.initiator, signaling.connected else { return }
        guard session.pc.signalingState == .stable else { return }
        guard force || Date().timeIntervalSince(session.lastOfferAt) >= 3.5 else { return }
        session.lastOfferAt = Date()

        let mandatory = [
            kRTCMediaConstraintsOfferToReceiveAudio: kRTCMediaConstraintsValueTrue,
            kRTCMediaConstraintsOfferToReceiveVideo: kRTCMediaConstraintsValueFalse
        ]
        let constraints = RTCMediaConstraints(mandatoryConstraints: mandatory, optionalConstraints: nil)
        session.pc.offer(for: constraints) { [weak self, weak session] sdp, error in
            Task { @MainActor in
                guard let self, let session, self.sessions[session.id] === session, let sdp else {
                    if let error { self?.recordError("Create offer: \(error.localizedDescription)") }
                    return
                }
                let preferred = RTCSessionDescription(type: sdp.type, sdp: self.preferOpus(sdp.sdp))
                session.pc.setLocalDescription(preferred) { error in
                    Task { @MainActor in
                        guard self.sessions[session.id] === session else { return }
                        if let error {
                            self.recordError("Set local offer: \(error.localizedDescription)")
                            return
                        }
                        self.signaling.publishSignal(RideSignalPacket(
                            from: self.signaling.nodeID,
                            to: session.id,
                            type: .offer,
                            payload: preferred.sdp
                        ))
                        self.diagnostics.offersSent += 1
                        self.refreshDiagnostics()
                    }
                }
            }
        }
    }

    private func handleSignal(_ signal: RideSignalPacket) {
        switch signal.type {
        case .offer:
            handleOffer(signal)
        case .answer:
            handleAnswer(signal)
        case .candidate:
            handleCandidate(signal)
        case .bye:
            closePeer(signal.from)
        }
    }

    private func handleOffer(_ signal: RideSignalPacket) {
        if let existing = sessions[signal.from] {
            if existing.pc.iceConnectionState == .failed || existing.pc.iceConnectionState == .closed {
                replacePeerForIncomingOffer(signal.from)
            } else if existing.pc.signalingState == .haveRemoteOffer {
                // Duplicate offer while an answer is already being produced.
                return
            }
        }

        guard let session = ensurePeer(signal.from, allowOffer: false) else { return }
        let remote = RTCSessionDescription(type: .offer, sdp: preferOpus(signal.payload))
        session.pc.setRemoteDescription(remote) { [weak self, weak session] error in
            Task { @MainActor in
                guard let self, let session, self.sessions[session.id] === session else { return }
                if let error {
                    self.recordError("Set remote offer: \(error.localizedDescription)")
                    return
                }
                session.remoteDescriptionSet = true
                self.flushCandidates(session)
                let mandatory = [
                    kRTCMediaConstraintsOfferToReceiveAudio: kRTCMediaConstraintsValueTrue,
                    kRTCMediaConstraintsOfferToReceiveVideo: kRTCMediaConstraintsValueFalse
                ]
                let constraints = RTCMediaConstraints(mandatoryConstraints: mandatory, optionalConstraints: nil)
                session.pc.answer(for: constraints) { sdp, error in
                    Task { @MainActor in
                        guard self.sessions[session.id] === session, let sdp else {
                            if let error { self.recordError("Create answer: \(error.localizedDescription)") }
                            return
                        }
                        let preferred = RTCSessionDescription(type: sdp.type, sdp: self.preferOpus(sdp.sdp))
                        session.pc.setLocalDescription(preferred) { error in
                            Task { @MainActor in
                                guard self.sessions[session.id] === session else { return }
                                if let error {
                                    self.recordError("Set local answer: \(error.localizedDescription)")
                                    return
                                }
                                self.signaling.publishSignal(RideSignalPacket(
                                    from: self.signaling.nodeID,
                                    to: signal.from,
                                    type: .answer,
                                    payload: preferred.sdp
                                ))
                                self.diagnostics.answersSent += 1
                                self.refreshDiagnostics()
                            }
                        }
                    }
                }
            }
        }
    }

    private func handleAnswer(_ signal: RideSignalPacket) {
        guard let session = sessions[signal.from] ?? ensurePeer(signal.from, allowOffer: false) else { return }
        guard session.pc.signalingState == .haveLocalOffer else {
            // Ignore a delayed/duplicate answer from an older negotiation.
            return
        }
        let remote = RTCSessionDescription(type: .answer, sdp: preferOpus(signal.payload))
        session.pc.setRemoteDescription(remote) { [weak self, weak session] error in
            Task { @MainActor in
                guard let self, let session, self.sessions[session.id] === session else { return }
                if let error {
                    self.recordError("Set remote answer: \(error.localizedDescription)")
                    return
                }
                session.remoteDescriptionSet = true
                self.flushCandidates(session)
                self.refreshDiagnostics()
            }
        }
    }

    private func handleCandidate(_ signal: RideSignalPacket) {
        guard let session = sessions[signal.from] ?? ensurePeer(signal.from, allowOffer: false) else { return }
        let key = "\(signal.mid)|\(signal.line)|\(signal.payload)"
        guard session.seenCandidateKeys.insert(key).inserted else { return }

        let candidate = RTCIceCandidate(sdp: signal.payload, sdpMLineIndex: signal.line, sdpMid: signal.mid)
        if session.remoteDescriptionSet {
            session.pc.add(candidate) { [weak self] error in
                if let error {
                    Task { @MainActor in self?.recordError("ICE candidate: \(error.localizedDescription)") }
                }
            }
        } else {
            session.pendingCandidates.append(candidate)
        }
    }

    private func flushCandidates(_ session: PeerSession) {
        let pending = session.pendingCandidates
        session.pendingCandidates.removeAll()
        pending.forEach { candidate in
            session.pc.add(candidate) { [weak self] error in
                if let error {
                    Task { @MainActor in self?.recordError("Pending ICE: \(error.localizedDescription)") }
                }
            }
        }
    }

    private func replacePeerForIncomingOffer(_ id: UUID) {
        if let old = sessions.removeValue(forKey: id) {
            old.disconnectTask?.cancel()
            old.pc.close()
        }
        speechStateByPeer[id] = false
        signaling.markPeerConnected(id, connected: false)
    }

    private func closePeer(_ id: UUID) {
        if let channel = hybridChannels.removeValue(forKey:id) { channel.delegate = nil; channel.close() }
        if let session = sessions.removeValue(forKey: id) {
            session.disconnectTask?.cancel()
            session.pc.close()
        }
        speechStateByPeer.removeValue(forKey: id)
        updateRemoteSpeechFromPeerStates()
        signaling.markPeerConnected(id, connected: false)
        applyVoiceEnabled()
        refreshDiagnostics()
    }

    private func startOfferRetryTimer() {
        offerRetryTimer?.invalidate()
        offerRetryTimer = Timer.scheduledTimer(withTimeInterval: batterySmart ? 5.0 : 3.0, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.running else { return }
                var staleNegotiations: [UUID] = []
                for session in Array(self.sessions.values) where session.initiator && !session.connected {
                    if session.pc.signalingState == .stable {
                        self.maybeCreateOffer(session)
                    } else if Date().timeIntervalSince(session.lastOfferAt) > 8 {
                        staleNegotiations.append(session.id)
                    }
                }
                staleNegotiations.forEach { self.rebuildPeer($0, reason: "stale negotiation") }
                self.peers = self.signaling.peers
                self.refreshDiagnostics()
            }
        }
    }

    private func handleIceState(_ state: RTCIceConnectionState, peerID: UUID) {
        guard let session = sessions[peerID] else { return }
        switch state {
        case .connected, .completed:
            session.disconnectTask?.cancel()
            session.disconnectTask = nil
            session.recoveryAttempts = 0
            if session.lastQuality == .reconnecting { session.lastQuality = .good }
            markConnected(peerID, connected: true)
            signaling.updatePeerQuality(peerID, quality: session.lastQuality)
            peers = signaling.peers

        case .disconnected:
            // Mobile radios routinely report brief DISCONNECTED transitions while
            // changing Wi-Fi/cellular paths. Keep the rider visually connected for
            // a grace period instead of flashing in/out of the room.
            signaling.updatePeerQuality(peerID, quality: .reconnecting)
            peers = signaling.peers
            scheduleDisconnectRecovery(for: session)
            statusText = "RECONNECTING…"

        case .failed:
            session.disconnectTask?.cancel()
            session.disconnectTask = nil
            signaling.updatePeerQuality(peerID, quality: .reconnecting)
            peers = signaling.peers
            markConnected(peerID, connected: false)
            recoverPeer(peerID, reason: "ICE failed")

        case .closed:
            markConnected(peerID, connected: false)

        default:
            break
        }
    }

    private func scheduleDisconnectRecovery(for session: PeerSession) {
        guard session.disconnectTask == nil else { return }
        let id = session.id
        session.disconnectTask = Task { @MainActor [weak self, weak session] in
            try? await Task.sleep(nanoseconds: 4_000_000_000)
            guard !Task.isCancelled,
                  let self,
                  let session,
                  self.sessions[id] === session else { return }
            session.disconnectTask = nil
            let state = session.pc.iceConnectionState
            guard state == .disconnected || state == .failed else { return }
            self.markConnected(id, connected: false)
            self.recoverPeer(id, reason: "ICE disconnected")
        }
    }

    private func recoverPeer(_ peerID: UUID, reason: String) {
        guard running, let session = sessions[peerID] else { return }
        let now = Date()
        guard now.timeIntervalSince(session.lastRecoveryAt) >= 2 else { return }
        session.lastRecoveryAt = now
        session.recoveryAttempts += 1
        statusText = "RECONNECTING…"

        // On an established stable connection, use a standards-based ICE restart
        // first. If negotiation itself is wedged, rebuild just that peer session.
        if session.initiator, session.pc.signalingState == .stable {
            diagnostics.connectionRecoveries += 1
            session.pc.restartIce()
            maybeCreateOffer(session, force: true)
        } else {
            rebuildPeer(peerID, reason: reason)
        }
        refreshDiagnostics()
    }

    private func rebuildPeer(_ peerID: UUID, reason: String) {
        guard running else { return }
        if let old = sessions.removeValue(forKey: peerID) {
            old.disconnectTask?.cancel()
            old.pc.close()
        }
        speechStateByPeer[peerID] = false
        updateRemoteSpeechFromPeerStates()
        signaling.markPeerConnected(peerID, connected: false)
        diagnostics.connectionRecoveries += 1

        // Tell the far side to clear any stale negotiation before the deterministic
        // initiator creates the replacement offer.
        signaling.publishSignal(RideSignalPacket(
            from: signaling.nodeID,
            to: peerID,
            type: .bye
        ))
        _ = ensurePeer(peerID, allowOffer: true)
        refreshDiagnostics()
    }

    private func recoverConnectionsAfterInterruption() {
        guard running else { return }
        for session in Array(sessions.values) {
            switch session.pc.iceConnectionState {
            case .failed:
                recoverPeer(session.id, reason: "post-call ICE failed")
            case .disconnected:
                scheduleDisconnectRecovery(for: session)
            default:
                break
            }
        }
    }

    private func markConnected(_ peerID: UUID, connected: Bool) {
        guard let session = sessions[peerID] else { return }
        session.connected = connected
        signaling.markPeerConnected(peerID, connected: connected)
        peers = signaling.peers
        if !connected {
            speechStateByPeer[peerID] = false
            updateRemoteSpeechFromPeerStates()
        }
        applyVoiceEnabled()
        refreshDiagnostics()
    }

    private func handleSignalingRestored() {
        guard running else { return }
        statusText = sessions.values.contains(where: { $0.connected }) ? "VOICE READY" : "RECONNECTING…"

        // Fast rejoin: keep the same room identity and peer objects. Any disconnected
        // deterministic initiator restarts ICE immediately instead of waiting for the
        // normal retry timer. Responders keep listening for the far-side offer.
        for session in Array(sessions.values) where !session.connected {
            session.lastRecoveryAt = .distantPast
            if session.initiator, session.pc.signalingState == .stable {
                session.pc.restartIce()
                maybeCreateOffer(session, force: true)
            } else if session.pc.iceConnectionState == .failed || session.pc.iceConnectionState == .closed {
                rebuildPeer(session.id, reason: "signaling restored")
            }
        }
        refreshDiagnostics()
    }

    private func startQualityStatsTimer() {
        qualityStatsTimer?.invalidate()
        qualityStatsTimer = Timer.scheduledTimer(withTimeInterval: batterySmart ? 4.0 : 2.5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.pollConnectionQuality() }
        }
        pollConnectionQuality()
    }

    private func pollConnectionQuality() {
        guard running else { return }
        for session in Array(sessions.values) {
            guard session.connected else {
                session.lastQuality = .reconnecting
                signaling.updatePeerQuality(session.id, quality: .reconnecting)
                continue
            }

            let peerID = session.id
            session.pc.statistics { [weak self, weak session] report in
                var packetsReceived: Double?
                var packetsLost: Double?
                var jitterSeconds: Double?
                var rttSeconds: Double?

                for stat in report.statistics.values {
                    let kind = ((stat.values["kind"] as? String) ?? (stat.values["mediaType"] as? String) ?? "").lowercased()
                    if stat.type == "inbound-rtp", kind == "audio" {
                        packetsReceived = Self.statDouble(stat.values["packetsReceived"]) ?? packetsReceived
                        packetsLost = Self.statDouble(stat.values["packetsLost"]) ?? packetsLost
                        jitterSeconds = Self.statDouble(stat.values["jitter"]) ?? jitterSeconds
                    }

                    if stat.type == "candidate-pair" {
                        let state = (stat.values["state"] as? String)?.lowercased() ?? ""
                        let nominated = Self.statBool(stat.values["nominated"]) ?? false
                        let selected = Self.statBool(stat.values["selected"]) ?? false
                        if state == "succeeded" && (nominated || selected || rttSeconds == nil) {
                            rttSeconds = Self.statDouble(stat.values["currentRoundTripTime"]) ?? rttSeconds
                        }
                    } else if stat.type == "remote-inbound-rtp", kind == "audio", rttSeconds == nil {
                        rttSeconds = Self.statDouble(stat.values["roundTripTime"]) ?? rttSeconds
                    }
                }

                Task { @MainActor in
                    guard let self, let session, self.sessions[peerID] === session, session.connected else { return }
                    let received = packetsReceived ?? session.lastPacketsReceived ?? 0
                    let lost = packetsLost ?? session.lastPacketsLost ?? 0
                    let previousReceived = session.lastPacketsReceived ?? received
                    let previousLost = session.lastPacketsLost ?? lost
                    let deltaReceived = max(0, received - previousReceived)
                    let deltaLost = max(0, lost - previousLost)
                    let deltaTotal = deltaReceived + deltaLost
                    let lossPercent = deltaTotal > 0 ? (deltaLost / deltaTotal) * 100 : 0
                    let jitterMs = max(0, (jitterSeconds ?? 0) * 1000)
                    let rttMs = max(0, (rttSeconds ?? 0) * 1000)

                    session.lastPacketsReceived = received
                    session.lastPacketsLost = lost
                    session.lastRTTMs = rttSeconds == nil ? session.lastRTTMs : rttMs
                    session.lastJitterMs = jitterSeconds == nil ? session.lastJitterMs : jitterMs
                    session.lastLossPercent = lossPercent

                    let effectiveRTT = session.lastRTTMs ?? 120
                    let effectiveJitter = session.lastJitterMs ?? 20
                    let quality: RiderConnectionQuality
                    if lossPercent >= 8 || effectiveRTT >= 450 || effectiveJitter >= 90 {
                        quality = .poor
                    } else if lossPercent < 2 && effectiveRTT < 170 && effectiveJitter < 35 {
                        quality = .excellent
                    } else {
                        quality = .good
                    }

                    if session.lastQuality == quality {
                        session.qualityStreak += 1
                    } else {
                        session.lastQuality = quality
                        session.qualityStreak = 1
                    }

                    // Require two consecutive quality samples before changing the
                    // sender cap. This prevents bitrate "flapping" on a single bad
                    // cellular sample while still reacting within a few seconds.
                    if session.qualityStreak >= 2 {
                        self.applyAdaptiveOpusPolicy(to: session, quality: quality)
                    }

                    self.signaling.updatePeerQuality(peerID, quality: quality)
                    self.peers = self.signaling.peers
                    self.refreshDiagnostics()
                }
            }
        }
    }

    /// Conservative adaptive Opus sender cap.  We keep the proven SDP/FEC/DTX
    /// negotiation unchanged for Android compatibility and only adjust the RTP
    /// sender's maximum bitrate in-place.  FEC remains enabled at all qualities;
    /// changing it dynamically would require renegotiation and is intentionally
    /// deferred until cross-platform testing proves it is safe.
    private func applyAdaptiveOpusPolicy(to session: PeerSession, quality: RiderConnectionQuality) {
        guard session.connected else { return }

        let lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
        let targetBps: Int
        switch quality {
        case .excellent:
            targetBps = lowPower ? 20_000 : 24_000
        case .good:
            targetBps = lowPower ? 18_000 : 20_000
        case .poor, .reconnecting:
            targetBps = 16_000
        }

        guard session.lastAppliedBitrateBps != targetBps else { return }
        for sender in session.pc.senders {
            guard sender.track?.kind.lowercased() == "audio" else { continue }
            let parameters = sender.parameters
            guard !parameters.encodings.isEmpty else { continue }
            for encoding in parameters.encodings {
                encoding.maxBitrateBps = NSNumber(value: targetBps)
            }
            sender.parameters = parameters
            session.lastAppliedBitrateBps = targetBps
        }
        diagnostics.adaptiveOpusBitrateKbps = targetBps / 1000
    }

    private func startSpeechStatsTimer() {
        let lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
        // No music: sample very lightly to save battery. Once another media app
        // starts, poll fast enough for natural local/remote speech ducking.
        let initial = lowPower ? 0.95 : (batterySmart ? 0.80 : 0.65)
        scheduleSpeechStatsTimer(interval: initial)
    }

    private func scheduleSpeechStatsTimer(interval: TimeInterval) {
        let clamped = max(0.14, min(interval, 1.20))
        guard speechStatsTimer == nil || abs(speechStatsInterval - clamped) > 0.03 else { return }
        speechStatsTimer?.invalidate()
        speechStatsInterval = clamped
        speechStatsTimer = Timer.scheduledTimer(withTimeInterval: clamped, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.pollSpeechLevels() }
        }
    }

    private func pollSpeechLevels() {
        guard running, !systemInterrupted else {
            setRemoteSpeechState(false)
            setLocalSpeechState(false)
            return
        }

        // Smart duck analysis is useful only while other media is playing.
        // Avoid expensive peer statistics polling during silent rides; the cheap
        // isOtherAudioPlaying check lets monitoring wake automatically when music starts.
#if !targetEnvironment(simulator)
        let otherAudioPlaying = AVAudioSession.sharedInstance().isOtherAudioPlaying
        let lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
        if otherAudioPlaying || smartDuckingActive {
            // While music is present, responsiveness matters more than a few extra
            // statistics calls. Explicit WebRTC VAD can still trigger immediately.
            scheduleSpeechStatsTimer(interval: lowPower ? 0.24 : 0.18)
        } else {
            scheduleSpeechStatsTimer(interval: lowPower ? 0.95 : (batterySmart ? 0.80 : 0.65))
        }

        if otherAudioPlaying && !otherAudioWasPlaying {
            // vc17 behavior: let newly-started music settle briefly before speech
            // gating becomes aggressive, so the first playback transient is ignored.
            otherAudioWasPlaying = true
            musicBaselineUntil = Date().addingTimeInterval(0.6)
            speechStateByPeer.removeAll()
            localSpeechGate.reset()
            setRemoteSpeechState(false)
            setLocalSpeechState(false)
        } else if !otherAudioPlaying {
            otherAudioWasPlaying = false
            musicBaselineUntil = .distantPast
        }

        if !otherAudioPlaying && !smartDuckingActive {
            speechStateByPeer.removeAll()
            localSpeechGate.reset()
            setRemoteSpeechState(false)
            setLocalSpeechState(false)
            return
        }

        if otherAudioPlaying && Date() < musicBaselineUntil {
            return
        }
#endif

        let connectedSessions = sessions.values.filter(\.connected)
        guard !connectedSessions.isEmpty else {
            speechStateByPeer.removeAll()
            setRemoteSpeechState(false)
            if userMuted { setLocalSpeechState(false) }
            return
        }

        let localProbePeer = connectedSessions.first?.id
        for session in connectedSessions {
            let peerID = session.id
            let collectLocal = peerID == localProbePeer && !userMuted
            session.pc.statistics { [weak self, weak session] report in
                var remoteLevel: Double?
                var remoteTotalEnergy: Double?
                var remoteTotalDuration: Double?
                var remoteVoiceFlag: Bool?

                var localLevel: Double?
                var localTotalEnergy: Double?
                var localTotalDuration: Double?
                var localVoiceFlag: Bool?

                for stat in report.statistics.values {
                    let kind = ((stat.values["kind"] as? String) ?? (stat.values["mediaType"] as? String) ?? "").lowercased()
                    guard kind == "audio" || stat.type == "media-source" else { continue }

                    if stat.type == "inbound-rtp" {
                        remoteLevel = Self.maxStatLevel(remoteLevel, stat.values["audioLevel"])
                        remoteTotalEnergy = Self.statDouble(stat.values["totalAudioEnergy"]) ?? remoteTotalEnergy
                        remoteTotalDuration = Self.statDouble(stat.values["totalSamplesDuration"]) ?? remoteTotalDuration
                        remoteVoiceFlag = Self.statBool(stat.values["voiceActivityFlag"]) ?? remoteVoiceFlag
                    } else if collectLocal && (stat.type == "media-source" || stat.type == "track" || stat.type == "outbound-rtp") {
                        localLevel = Self.maxStatLevel(localLevel, stat.values["audioLevel"])
                        localTotalEnergy = Self.statDouble(stat.values["totalAudioEnergy"]) ?? localTotalEnergy
                        localTotalDuration = Self.statDouble(stat.values["totalSamplesDuration"]) ?? localTotalDuration
                        localVoiceFlag = Self.statBool(stat.values["voiceActivityFlag"]) ?? localVoiceFlag
                    }
                }

                Task { @MainActor in
                    guard let self,
                          let session,
                          self.sessions[peerID] === session,
                          session.connected else { return }

                    var resolvedRemoteLevel = remoteLevel
                    if resolvedRemoteLevel == nil,
                       let energy = remoteTotalEnergy,
                       let duration = remoteTotalDuration,
                       let previousEnergy = session.lastTotalAudioEnergy,
                       let previousDuration = session.lastTotalSamplesDuration {
                        let deltaDuration = duration - previousDuration
                        let deltaEnergy = energy - previousEnergy
                        if deltaDuration > 0, deltaEnergy >= 0 {
                            resolvedRemoteLevel = sqrt(deltaEnergy / deltaDuration)
                        }
                    }
                    if let energy = remoteTotalEnergy { session.lastTotalAudioEnergy = energy }
                    if let duration = remoteTotalDuration { session.lastTotalSamplesDuration = duration }

                    let remoteActive = session.speechGate.update(level: resolvedRemoteLevel, explicitVoice: remoteVoiceFlag)
                    self.speechStateByPeer[peerID] = remoteActive
                    self.updateRemoteSpeechFromPeerStates()

                    if collectLocal {
                        var resolvedLocalLevel = localLevel
                        if resolvedLocalLevel == nil,
                           let energy = localTotalEnergy,
                           let duration = localTotalDuration,
                           let previousEnergy = self.localLastTotalAudioEnergy,
                           let previousDuration = self.localLastTotalSamplesDuration {
                            let deltaDuration = duration - previousDuration
                            let deltaEnergy = energy - previousEnergy
                            if deltaDuration > 0, deltaEnergy >= 0 {
                                resolvedLocalLevel = sqrt(deltaEnergy / deltaDuration)
                            }
                        }
                        if let energy = localTotalEnergy { self.localLastTotalAudioEnergy = energy }
                        if let duration = localTotalDuration { self.localLastTotalSamplesDuration = duration }
                        let localActive = self.localSpeechGate.update(level: resolvedLocalLevel, explicitVoice: localVoiceFlag)
                        self.setLocalSpeechState(localActive)
                    }
                }
            }
        }
    }

    private static func statDouble(_ value: Any?) -> Double? {
        if let number = value as? NSNumber { return number.doubleValue }
        if let value = value as? Double { return value }
        if let value = value as? Float { return Double(value) }
        if let value = value as? Int { return Double(value) }
        return nil
    }

    private static func statBool(_ value: Any?) -> Bool? {
        if let value = value as? Bool { return value }
        if let number = value as? NSNumber { return number.boolValue }
        if let text = value as? String {
            if text == "1" || text.lowercased() == "true" { return true }
            if text == "0" || text.lowercased() == "false" { return false }
        }
        return nil
    }

    private static func maxStatLevel(_ current: Double?, _ value: Any?) -> Double? {
        guard let level = statDouble(value) else { return current }
        return max(current ?? 0, level)
    }

    private func updateRemoteSpeechFromPeerStates() {
        setRemoteSpeechState(speechStateByPeer.values.contains(true))
    }

    private func setRemoteSpeechState(_ active: Bool) {
        guard remoteSpeechActive != active else { return }
        remoteSpeechActive = active
        diagnostics.remoteSpeechActive = active
        updateSmartDuckingState()
        applyVoiceEnabled()
        refreshDiagnostics()
    }

    private func setLocalSpeechState(_ active: Bool) {
        let effective = userMuted ? false : active
        guard localSpeechActive != effective else { return }
        localSpeechActive = effective
        diagnostics.localSpeechActive = effective
        updateSmartDuckingState()
        refreshDiagnostics()
    }

    private func updateSmartDuckingState() {
        let active = !systemInterrupted && (remoteSpeechActive || localSpeechActive)
        guard smartDuckingActive != active else { return }
        smartDuckingActive = active
        diagnostics.smartDuckingActive = active
    }

    private func peerID(for pc: RTCPeerConnection) -> UUID? {
        sessions.first(where: { $0.value.pc === pc })?.key
    }

    private func recordError(_ text: String) {
        diagnostics.lastError = text
        refreshDiagnostics()
    }

    private func refreshDiagnostics() {
        diagnostics.signalingConnected = signaling.connected
        diagnostics.knownRiders = signaling.peers.count
        diagnostics.voicePeersConnected = sessions.values.filter(\.connected).count
        diagnostics.reconnects = signaling.reconnects
        diagnostics.remoteSpeechActive = remoteSpeechActive
        diagnostics.localSpeechActive = localSpeechActive
        diagnostics.smartDuckingActive = smartDuckingActive
        diagnostics.opusDtxEnabled = true
        diagnostics.motorcycleNoiseGuardEnabled = true
        if diagnostics.lastError.isEmpty { diagnostics.lastError = signaling.lastError }
    }

    private func preferOpus(_ sdp: String) -> String {
        let separator = sdp.contains("\r\n") ? "\r\n" : "\n"
        var lines = sdp.components(separatedBy: separator)
        guard let opusIndex = lines.firstIndex(where: { $0.lowercased().contains("opus/48000") }) else { return sdp }
        let opusLine = lines[opusIndex]
        guard let colon = opusLine.firstIndex(of: ":"),
              let space = opusLine[colon...].firstIndex(of: " ") else { return sdp }
        let payload = String(opusLine[opusLine.index(after: colon)..<space])

        if let audioIndex = lines.firstIndex(where: { $0.hasPrefix("m=audio ") }) {
            var parts = lines[audioIndex].split(separator: " ").map(String.init)
            if parts.count > 3, let existing = parts.firstIndex(of: payload) {
                parts.remove(at: existing)
                parts.insert(payload, at: 3)
                lines[audioIndex] = parts.joined(separator: " ")
            }
        }

        // Motorcycle voice profile: mono Opus, in-band FEC and DTX. DTX reduces
        // radio/codec work during silence; 24 kbps is ample for intelligible group voice.
        let desired: [(String, String)] = [
            ("minptime", "10"),
            ("useinbandfec", "1"),
            ("usedtx", "1"),
            ("maxaveragebitrate", "24000"),
            ("stereo", "0"),
            ("sprop-stereo", "0")
        ]
        let fmtpPrefix = "a=fmtp:\(payload)"
        if let fmtpIndex = lines.firstIndex(where: { $0.hasPrefix(fmtpPrefix) }) {
            let existingText = lines[fmtpIndex].dropFirst(fmtpPrefix.count).trimmingCharacters(in: .whitespaces)
            var params = existingText.split(separator: ";").map { String($0).trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
            let desiredKeys = Set(desired.map(\.0))
            params.removeAll { item in
                guard let key = item.split(separator: "=", maxSplits: 1).first else { return false }
                return desiredKeys.contains(String(key).lowercased())
            }
            params.append(contentsOf: desired.map { "\($0.0)=\($0.1)" })
            lines[fmtpIndex] = fmtpPrefix + " " + params.joined(separator: ";")
        } else {
            let fmtp = fmtpPrefix + " " + desired.map { "\($0.0)=\($0.1)" }.joined(separator: ";")
            lines.insert(fmtp, at: min(opusIndex + 1, lines.count))
        }

        // vc20.1 cross-platform compatibility hotfix:
        // Do not rewrite SDP ptime/maxptime here. Android and iOS already
        // negotiate Opus with a normal 20 ms packetization in practice, while
        // manually appending these attributes can make the SDP incompatible
        // with some Android/WebRTC builds. Low-latency receive tuning remains
        // local to the iOS RTCConfiguration above.


        return lines.joined(separator: separator)
    }

}

extension WebRTCVoiceService: RTCPeerConnectionDelegate {
    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    nonisolated func peerConnectionShouldNegotiate(_ peerConnection: RTCPeerConnection) {}

    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceConnectionState) {
        Task { @MainActor [weak self] in
            guard let self, let id = self.peerID(for: peerConnection) else { return }
            self.handleIceState(newState, peerID: id)
        }
    }

    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didChange newState: RTCIceGatheringState) {}

    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        Task { @MainActor [weak self] in
            guard let self, let id = self.peerID(for: peerConnection) else { return }
            self.signaling.publishSignal(RideSignalPacket(
                from: self.signaling.nodeID,
                to: id,
                type: .candidate,
                payload: candidate.sdp,
                mid: candidate.sdpMid ?? "",
                line: candidate.sdpMLineIndex
            ))
            self.diagnostics.candidatesSent += 1
            self.refreshDiagnostics()
        }
    }

    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    nonisolated func peerConnection(_ peerConnection: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {
        Task { @MainActor [weak self] in
            guard let self, let peer = self.peerID(for:peerConnection) else { dataChannel.close(); return }
            self.registerHybrid(dataChannel,peer:peer)
        }
    }
}


extension WebRTCVoiceService: RTCDataChannelDelegate {
    nonisolated func dataChannelDidChangeState(_ dataChannel: RTCDataChannel) {
        Task { @MainActor [weak self] in self?.refreshDiagnostics() }
    }
    nonisolated func dataChannel(_ dataChannel: RTCDataChannel, didReceiveMessageWith buffer: RTCDataBuffer) {
        guard buffer.isBinary, buffer.data.count <= 2048 else { return }
        let data = buffer.data
        let arrived = ProcessInfo.processInfo.systemUptime
        Task { @MainActor [weak self] in
            guard let self, self.running, self.hybridMode,
                  ProcessInfo.processInfo.systemUptime-arrived < 0.14,
                  let peer = self.hybridChannels.first(where:{ $0.value === dataChannel })?.key else { return }
            self.onHybridPacket?(peer,data)
        }
    }
}
