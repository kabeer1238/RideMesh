import Foundation
import NearbyConnections

/// Main-queue Nearby transport. RM34 discovery is isolated by ride token before connection.
final class HybridNearby: NSObject, ConnectionManagerDelegate, AdvertiserDelegate, DiscovererDelegate {
    static let serviceID = "in.autopilotindia.ridemesh.hybrid34"
    private let manager = ConnectionManager(serviceID: HybridNearby.serviceID, strategy: .cluster)
    private lazy var advertiser = Advertiser(connectionManager: manager)
    private lazy var discoverer = Discoverer(connectionManager: manager)
    private let node: UUID
    private let token: String
    private let name: String
    private var info: Data { Data("RM34|0|\(token)|\(name)".utf8) }
    private var endpoints = Set<EndpointID>()
    private var identities: [EndpointID:UUID] = [:]
    private var found = Set<EndpointID>()
    private var pending: [EndpointID:TimeInterval] = [:]
    private var helloAttempts: [EndpointID:Int] = [:]
    private var queue: [EndpointID:[UUID:(Data,TimeInterval)]] = [:]
    private var inFlight: [EndpointID:(PayloadID,TimeInterval,CancellationToken)] = [:]
    private var timer: Timer?
    private var active = false
    var receive: (UUID,Data) -> Void = { _,_ in }
    var onChange: () -> Void = {}
    var onError: (String) -> Void = { _ in }
    var peers: Set<UUID> { Set(identities.values) }
    init(node: UUID, rideCode: String, name: String) {
        self.node = node; token = RideMeshOfflineWireProtocol.rideToken(for:rideCode)
        self.name = String(name.replacingOccurrences(of:"|",with:"/").prefix(24))
        super.init(); manager.delegate = self; advertiser.delegate = self; discoverer.delegate = self
    }
    func start() {
        active = true
        advertiser.startAdvertising(using:info) { [weak self] error in
            if let error { DispatchQueue.main.async { self?.onError(error.localizedDescription) } }
        }
        discoverer.startDiscovery() { [weak self] error in
            if let error { DispatchQueue.main.async { self?.onError(error.localizedDescription) } }
        }
        timer = Timer.scheduledTimer(withTimeInterval:1,repeats:true) { [weak self] _ in self?.tick() }
    }
    func stop() {
        active = false; timer?.invalidate(); timer = nil
        advertiser.stopAdvertising(); discoverer.stopDiscovery()
        for endpoint in endpoints { manager.disconnect(from:endpoint) }
        for (_,_,token) in inFlight.values { token.cancel() }
        endpoints.removeAll(); identities.removeAll(); queue.removeAll(); inFlight.removeAll(); pending.removeAll(); found.removeAll()
    }
    private func allowed(_ context: Data) -> Bool {
        guard let text = String(data:context,encoding:.utf8) else { return false }
        let p = text.split(separator:"|",maxSplits:3,omittingEmptySubsequences:false)
        return p.count == 4 && p[0] == "RM34" && p[1] == "0" && p[2] == token
    }
    private func raw(_ data: Data, to endpoint: EndpointID) { _ = manager.send(data,to:[endpoint]) }
    private func hello(_ endpoint: EndpointID, ack: Bool = false) {
        raw(Data("\(ack ? "HELLO_ACK" : "HELLO")|\(token)|\(node.uuidString.lowercased())|\(name)|iPhone".utf8),to:endpoint)
    }
    private func tick() {
        guard active else { return }
        let now = ProcessInfo.processInfo.systemUptime
        for endpoint in endpoints where identities[endpoint] == nil {
            let attempts = helloAttempts[endpoint,default:0]
            if attempts >= 10 { manager.disconnect(from:endpoint) }
            else { helloAttempts[endpoint] = attempts+1; hello(endpoint) }
        }
        for (endpoint,time) in pending where now-time > 12 { pending.removeValue(forKey:endpoint); manager.disconnect(from:endpoint) }
        for endpoint in found where !endpoints.contains(endpoint) && pending[endpoint] == nil && endpoints.count+pending.count < 7 {
            pending[endpoint] = now; discoverer.requestConnection(to:endpoint,using:info)
        }
        for (endpoint,flight) in inFlight where now-flight.1 > 1.5 {
            flight.2.cancel(); inFlight.removeValue(forKey:endpoint); queue.removeValue(forKey:endpoint); manager.disconnect(from:endpoint)
        }
        for endpoint in endpoints { drain(endpoint) }
    }
    func send(excluding: UUID?, data: Data) {
        guard active, let packet = HybridPacket.decode(data) else { return }
        for (endpoint,id) in identities where id != excluding {
            let bytes = Data([0x52,0x4d,0x44,0x31]) + data
            if packet.kind == 2 {
                if queue[endpoint] == nil { queue[endpoint] = [:] }
                if queue[endpoint]!.count < 8 || queue[endpoint]![packet.origin] != nil {
                    queue[endpoint]![packet.origin] = (bytes,ProcessInfo.processInfo.systemUptime)
                }
                drain(endpoint)
            } else { raw(bytes,to:endpoint) }
        }
    }
    private func drain(_ endpoint: EndpointID) {
        guard inFlight[endpoint] == nil, identities[endpoint] != nil else { return }
        let now = ProcessInfo.processInfo.systemUptime
        queue[endpoint] = queue[endpoint]?.filter { now-$0.value.1 <= 0.14 }
        guard let next = queue[endpoint]?.min(by:{ $0.value.1 < $1.value.1 }) else { return }
        queue[endpoint]?.removeValue(forKey:next.key)
        let id = Int64.random(in:1...Int64.max)
        let cancel = manager.send(next.value.0,to:[endpoint],id:id) { [weak self] error in
            if error != nil { DispatchQueue.main.async {
                if self?.inFlight[endpoint]?.0 == id { self?.inFlight.removeValue(forKey:endpoint) }
            } }
        }
        inFlight[endpoint] = (id,now,cancel)
    }
    func advertiser(_ advertiser: Advertiser, didReceiveConnectionRequestFrom endpointID: EndpointID,
                    with context: Data, connectionRequestHandler: @escaping (Bool) -> Void) {
        let accept = active && allowed(context) && (pending[endpointID] != nil || endpoints.count+pending.count < 7)
        if accept { pending[endpointID] = ProcessInfo.processInfo.systemUptime }
        connectionRequestHandler(accept)
    }
    func discoverer(_ discoverer: Discoverer, didFind endpointID: EndpointID, with context: Data) {
        guard active, allowed(context) else { return }; found.insert(endpointID); tick()
    }
    func discoverer(_ discoverer: Discoverer, didLose endpointID: EndpointID) { found.remove(endpointID) }
    func connectionManager(_ connectionManager: ConnectionManager, didReceive verificationCode: String,
                           from endpointID: EndpointID, verificationHandler: @escaping (Bool) -> Void) {
        verificationHandler(active && pending[endpointID] != nil)
    }
    func connectionManager(_ connectionManager: ConnectionManager, didChangeTo state: ConnectionState, for endpointID: EndpointID) {
        guard active else { manager.disconnect(from:endpointID); return }
        switch state {
        case .connected:
            pending.removeValue(forKey:endpointID); endpoints.insert(endpointID); hello(endpointID)
        case .disconnected, .rejected:
            pending.removeValue(forKey:endpointID); endpoints.remove(endpointID); identities.removeValue(forKey:endpointID)
            inFlight.removeValue(forKey:endpointID); queue.removeValue(forKey:endpointID); helloAttempts.removeValue(forKey:endpointID)
        case .connecting: break
        }
        onChange()
    }
    func connectionManager(_ connectionManager: ConnectionManager, didReceive data: Data, withID payloadID: PayloadID, from endpointID: EndpointID) {
        guard active, endpoints.contains(endpointID), data.count <= 2052 else { return }
        if data.starts(with:[0x52,0x4d,0x44,0x31]) {
            if let id = identities[endpointID] { receive(id,Data(data.dropFirst(4))) }; return
        }
        guard let text = String(data:data,encoding:.utf8) else { return }
        if text.hasPrefix("PING|") { raw(Data(text.replacingOccurrences(of:"PING|",with:"PONG|").utf8),to:endpointID); return }
        let p = text.split(separator:"|",maxSplits:4,omittingEmptySubsequences:false).map(String.init)
        guard p.count >= 4, p[0] == "HELLO" || p[0] == "HELLO_ACK" else { return }
        guard p[1] == token, let id = UUID(uuidString:p[2]), id != node,
              !identities.contains(where:{ $0.key != endpointID && $0.value == id }) else { manager.disconnect(from:endpointID); return }
        identities[endpointID] = id
        if p[0] == "HELLO" { hello(endpointID,ack:true) }; onChange()
    }
    func connectionManager(_ connectionManager: ConnectionManager, didReceiveTransferUpdate update: TransferUpdate, from endpointID: EndpointID, forPayload payloadID: PayloadID) {
        guard inFlight[endpointID]?.0 == payloadID else { return }
        if case .progress = update { return }
        inFlight.removeValue(forKey:endpointID); drain(endpointID)
    }
    func connectionManager(_ connectionManager: ConnectionManager, didReceive stream: InputStream, withID payloadID: PayloadID, from endpointID: EndpointID, cancellationToken token: CancellationToken) { token.cancel() }
    func connectionManager(_ connectionManager: ConnectionManager, didStartReceivingResourceWithID payloadID: PayloadID, from endpointID: EndpointID, at localURL: URL, withName name: String, cancellationToken token: CancellationToken) { token.cancel() }
}
