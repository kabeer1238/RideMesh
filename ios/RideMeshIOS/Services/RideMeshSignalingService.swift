import Foundation
import UIKit

@MainActor
final class RideMeshSignalingService: ObservableObject {
    @Published private(set) var connected = false
    @Published private(set) var peers: [RiderPeer] = []
    @Published private(set) var reconnects = 0
    @Published private(set) var lastError = ""

    var onSignal: ((RideSignalPacket) -> Void)?
    var onPeerSeen: ((RiderPeer) -> Void)?
    var onPeerExpired: ((UUID) -> Void)?
    var onTransportRestored: (() -> Void)?
    var onLocation: ((RiderLocationPacket) -> Void)?

    private let mqtt = MQTTSignalingClient()
    private let defaults = UserDefaults.standard
    private var presenceTimer: Timer?
    private var pruneTimer: Timer?
    private var peerMap: [UUID: RiderPeer] = [:]

    private var riderName = "Rider"
    private var deviceName = "iPhone"
    private var presenceTopic = ""
    private var signalTopic = ""
    private var locationTopic = ""
    private var subscriptionTopic = ""
    private var batterySmart = true
    private var lastPresenceReply = Date.distantPast

    var nodeID: UUID

    init() {
        if let saved = defaults.string(forKey: "beta4_webrtc_node_id"), let uuid = UUID(uuidString: saved) {
            nodeID = uuid
        } else {
            let uuid = UUID()
            nodeID = uuid
            defaults.set(uuid.uuidString.lowercased(), forKey: "beta4_webrtc_node_id")
        }

        mqtt.onState = { [weak self] state in
            Task { @MainActor in self?.handleMQTTState(state) }
        }
        mqtt.onPublish = { [weak self] topic, payload in
            Task { @MainActor in self?.handlePublish(topic: topic, payload: payload) }
        }
    }

    func start(rideCode: String, riderName: String, deviceName: String? = nil, batterySmart: Bool = true, hybrid: Bool = false) {
        stop()
        if hybrid { nodeID = UUID() }
        let safeRide = Self.sanitizeRideCode(rideCode)
        self.riderName = Self.sanitizeIdentity(riderName, fallback: "Rider", maxBytes: 48)
        self.deviceName = Self.sanitizeIdentity(deviceName ?? UIDevice.current.model, fallback: "iPhone", maxBytes: 64)
        self.batterySmart = batterySmart

        let base = hybrid ? "ridemesh/test/hybrid33/\(safeRide)" : "ridemesh/test/v3/\(safeRide)"
        presenceTopic = "\(base)/presence"
        signalTopic = "\(base)/signal"
        locationTopic = "\(base)/location"
        subscriptionTopic = "\(base)/#"
        peerMap.removeAll()
        peers = []
        lastError = ""
        lastPresenceReply = .distantPast

        let clientID = "ridemesh-ios-\(nodeID.uuidString.replacingOccurrences(of: "-", with: "").prefix(16).lowercased())"
        mqtt.start(clientID: clientID, subscriptionTopic: subscriptionTopic)
        startPruneTimer()
    }

    func stop() {
        publishSignal(RideSignalPacket(from: nodeID, to: RideMeshSignalCodec.broadcastID, type: .bye))
        presenceTimer?.invalidate()
        presenceTimer = nil
        pruneTimer?.invalidate()
        pruneTimer = nil
        mqtt.stop()
        connected = false
        peerMap.removeAll()
        peers = []
    }

    func publishSignal(_ packet: RideSignalPacket) {
        guard connected, !signalTopic.isEmpty else { return }
        mqtt.publish(topic: signalTopic, payload: RideMeshSignalCodec.encodeSignal(packet))
    }

    func publishLocation(_ packet: RiderLocationPacket) {
        guard connected, !locationTopic.isEmpty else { return }
        mqtt.publish(topic: locationTopic, payload: RideMeshSignalCodec.encodeLocation(packet))
    }

    private func handleMQTTState(_ state: MQTTSignalingClient.State) {
        switch state {
        case .connected:
            let wasDisconnected = !connected
            connected = true
            lastError = ""
            publishPresence()
            startPresenceTimer()
            if wasDisconnected { onTransportRestored?() }
        case .connecting:
            connected = false
        case .reconnecting:
            connected = false
            reconnects += 1
        case .failed(let message):
            connected = false
            lastError = message
        case .stopped:
            connected = false
        }
    }

    private func handlePublish(topic: String, payload: Data) {
        if topic == presenceTopic {
            guard let presence = RideMeshSignalCodec.decodePresence(payload), presence.origin != nodeID else { return }
            let previous = peerMap[presence.origin]
            let peer = RiderPeer(
                id: presence.origin,
                riderName: presence.riderName.isEmpty ? (previous?.riderName ?? "") : presence.riderName,
                deviceName: presence.deviceName.isEmpty ? (previous?.deviceName ?? "") : presence.deviceName,
                lastSeen: Date(),
                connected: previous?.connected ?? false,
                qualityBars: previous?.qualityBars ?? 1,
                connectionQuality: previous?.connectionQuality ?? .reconnecting
            )
            peerMap[presence.origin] = peer
            refreshPeerList()
            onPeerSeen?(peer)

            // vc17 balance: stable rooms use low presence traffic, but a newly
            // discovered rider gets an immediate reply so their rider list fills fast.
            if previous == nil, Date().timeIntervalSince(lastPresenceReply) > 1.2 {
                lastPresenceReply = Date()
                publishPresence()
            }
            return
        }

        if topic == locationTopic,
           let location = RideMeshSignalCodec.decodeLocation(payload),
           location.riderId != nodeID {
            onLocation?(location)
            return
        }

        if topic == signalTopic,
           let signal = RideMeshSignalCodec.decodeSignal(payload),
           signal.from != nodeID,
           signal.to == nodeID || signal.to == RideMeshSignalCodec.broadcastID {
            onSignal?(signal)
        }
    }

    private func publishPresence() {
        guard connected else { return }
        let packet = RidePresencePacket(
            origin: nodeID,
            timestampMs: Int64(Date().timeIntervalSince1970 * 1000),
            riderName: riderName,
            deviceName: deviceName
        )
        mqtt.publish(topic: presenceTopic, payload: RideMeshSignalCodec.encodePresence(packet))
    }

    private func startPresenceTimer() {
        presenceTimer?.invalidate()
        presenceTimer = Timer.scheduledTimer(withTimeInterval: batterySmart ? 12.0 : 5.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.publishPresence() }
        }
    }

    private func startPruneTimer() {
        pruneTimer?.invalidate()
        pruneTimer = Timer.scheduledTimer(withTimeInterval: batterySmart ? 8.0 : 5.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.prunePeers() }
        }
    }

    private func prunePeers() {
        let cutoff = Date().addingTimeInterval(-(batterySmart ? 38.0 : 22.0))
        let expired = peerMap.values.filter { $0.lastSeen < cutoff }.map(\.id)
        for id in expired {
            peerMap.removeValue(forKey: id)
            onPeerExpired?(id)
        }
        if !expired.isEmpty { refreshPeerList() }
    }

    func markPeerConnected(_ id: UUID, connected: Bool) {
        guard var peer = peerMap[id] else { return }
        peer.connected = connected
        if !connected {
            peer.connectionQuality = .reconnecting
            peer.qualityBars = RiderConnectionQuality.reconnecting.bars
        } else if peer.connectionQuality == .reconnecting {
            peer.connectionQuality = .good
            peer.qualityBars = RiderConnectionQuality.good.bars
        }
        peerMap[id] = peer
        refreshPeerList()
    }

    func updatePeerQuality(_ id: UUID, quality: RiderConnectionQuality) {
        guard var peer = peerMap[id] else { return }
        peer.connectionQuality = quality
        peer.qualityBars = quality.bars
        if quality != .reconnecting { peer.connected = true }
        peerMap[id] = peer
        refreshPeerList()
    }

    /// Called when iOS reports a Wi-Fi/cellular path transition. We preserve the
    /// Ride Code and peer identities, but move MQTT to the new route immediately
    /// instead of waiting for the old TCP socket to time out.
    func handleNetworkPathChange(isOnline: Bool) {
        guard isOnline else { return }
        mqtt.forceReconnect()
    }

    private func refreshPeerList() {
        peers = peerMap.values.sorted { $0.displayName.localizedCaseInsensitiveCompare($1.displayName) == .orderedAscending }
    }

    static func sanitizeRideCode(_ value: String) -> String {
        let upper = value.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        let filtered = upper.unicodeScalars.map { allowed.contains($0) ? Character(String($0)) : Character("_") }
        let result = String(filtered).prefix(32)
        return result.isEmpty ? "RIDE01" : String(result)
    }

    private static func sanitizeIdentity(_ value: String, fallback: String, maxBytes: Int) -> String {
        let clean = value.trimmingCharacters(in: .whitespacesAndNewlines)
        let source = clean.isEmpty ? fallback : clean
        var data = Data(source.utf8.prefix(maxBytes))
        while String(data: data, encoding: .utf8) == nil, !data.isEmpty { data.removeLast() }
        return String(data: data, encoding: .utf8) ?? fallback
    }
}
