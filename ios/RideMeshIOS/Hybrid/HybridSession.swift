import Foundation

@MainActor
final class HybridSession: ObservableObject {
    @Published private(set) var riders: [UUID:String] = [:]
    @Published private(set) var summary = "HYBRID READY"
    private let voice: WebRTCVoiceService
    private let audio = HybridAudio()
    private var router: HybridRouter?
    private var nearby: HybridNearby?
    private var timer: Timer?
    private var lastSeen: [UUID:TimeInterval] = [:]
    private var name = "Rider"
    private var active = false
    init(voice: WebRTCVoiceService) { self.voice = voice }
    func start(name: String, code: String) {
        stop(); active = true; self.name = name
        let router = HybridRouter(node:voice.localRiderID); self.router = router
        let nearby = HybridNearby(node:voice.localRiderID,rideCode:code,name:name); self.nearby = nearby
        router.localSend = { [weak nearby] in nearby?.send(excluding:$0,data:$1) }
        router.internetPeers = { [weak voice] in voice?.hybridPeerIDs ?? [] }
        router.internetSend = { [weak voice] in voice?.sendHybrid($0,$1) }
        router.deliver = { [weak self] in self?.receive($0) }
        nearby.receive = { [weak router] in router?.receive(from:$0,data:$1) }
        nearby.onChange = { [weak self] in self?.heartbeat() }
        nearby.onError = { [weak self] in self?.summary = "Nearby: \($0)" }
        voice.onHybridPacket = { [weak router] in router?.receive(from:$0,data:$1,internet:true) }
        audio.encoded = { [weak router] in router?.originate(kind:2,payload:$0) }
        audio.onError = { [weak self] in self?.summary = "Audio: \($0)" }
        nearby.start(); audio.setMuted(false); audio.start(); heartbeat()
        timer = Timer.scheduledTimer(withTimeInterval:2,repeats:true) { [weak self] _ in
            Task { @MainActor in self?.heartbeat() }
        }
    }
    func stop() {
        active = false; timer?.invalidate(); timer = nil; audio.stop(); nearby?.stop(); nearby = nil
        voice.onHybridPacket = nil; router = nil; riders.removeAll(); lastSeen.removeAll(); summary = "HYBRID STOPPED"
    }
    func mute(_ value: Bool) { audio.setMuted(value) }
    func interrupted(_ value: Bool) {
        guard active else { return }; if value { audio.stop() } else { audio.start() }
    }
    private func receive(_ packet: HybridPacket) {
        if packet.kind == 2 { audio.receive(packet) }
        if packet.kind == 3, let json = try? JSONSerialization.jsonObject(with:packet.payload) as? [String:Any],
           riders.count < 7 || riders[packet.origin] != nil {
            riders[packet.origin] = String((json["name"] as? String ?? "Rider").prefix(24))
            lastSeen[packet.origin] = ProcessInfo.processInfo.systemUptime
        }
    }
    private func heartbeat() {
        guard active else { return }
        let now = ProcessInfo.processInfo.systemUptime
        for (id,time) in lastSeen where now-time > 8 { riders.removeValue(forKey:id); lastSeen.removeValue(forKey:id) }
        let presence: [String:Any] = ["name":name,"device":"iPhone","gateways":voice.hybridPeerIDs.map { $0.uuidString.lowercased() }]
        if let data = try? JSONSerialization.data(withJSONObject:presence) { router?.originate(kind:3,payload:data) }
        summary = "\(riders.count+1) RIDERS • \(nearby?.peers.count ?? 0) LOCAL • \(voice.hybridPeerIDs.count) INTERNET • \(router?.relayed ?? 0) RELAYS"
    }
}
