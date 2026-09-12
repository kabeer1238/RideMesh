import Foundation

// Android vc33 RME1 version 2, big-endian, 73-byte header.
struct HybridPacket {
    var id = UUID()
    var origin: UUID
    var previous: UUID
    var sequence: UInt32
    var timestamp: UInt64
    var ttl: UInt8 = 6
    var hops: UInt8 = 0
    var kind: UInt8
    var payload: Data
    var internetHops: UInt8 = 0
    func encode() -> Data {
        var bytes: [UInt8] = [0x52,0x4d,0x45,0x31,2,kind,internetHops,ttl,hops]
        for uuid in [id,origin,previous] { var u = uuid.uuid; withUnsafeBytes(of: &u) { bytes += $0 } }
        func append(_ value: UInt64, _ count: Int) { for i in (0..<count).reversed() { bytes.append(UInt8(truncatingIfNeeded: value >> (8*i))) } }
        append(UInt64(sequence),4); append(timestamp,8); append(UInt64(payload.count),4)
        return Data(bytes) + payload
    }
    static func decode(_ data: Data) -> HybridPacket? {
        let b = [UInt8](data)
        guard b.count >= 73, b.count <= 2048, Array(b[0..<5]) == [0x52,0x4d,0x45,0x31,2],
              (1...4).contains(b[5]), b[6] <= 1, Int(b[7])+Int(b[8]) == 6 else { return nil }
        func number(_ start: Int, _ length: Int) -> UInt64 { b[start..<start+length].reduce(0) { ($0 << 8) | UInt64($1) } }
        func uuid(_ start: Int) -> UUID {
            let x = Array(b[start..<start+16])
            return UUID(uuid:(x[0],x[1],x[2],x[3],x[4],x[5],x[6],x[7],x[8],x[9],x[10],x[11],x[12],x[13],x[14],x[15]))
        }
        guard number(69,4) == b.count-73 else { return nil }
        return HybridPacket(id:uuid(9),origin:uuid(25),previous:uuid(41),sequence:UInt32(number(57,4)),
            timestamp:number(61,8),ttl:b[7],hops:b[8],kind:b[5],payload:Data(b.dropFirst(73)),internetHops:b[6])
    }
}

/// Confined to one serial executor by the controller. Pure Foundation for cross-platform tests.
final class HybridRouter {
    let node: UUID
    var localSend: (UUID?, Data) -> Void = { _,_ in }
    var internetSend: (UUID,Data) -> Void = { _,_ in }
    var internetPeers: () -> Set<UUID> = { [] }
    var deliver: (HybridPacket) -> Void = { _ in }
    var clock: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
    private var seen = Set<UUID>()
    private var order = [UUID]()
    private var audioSequence: UInt32 = 0
    private var controlSequence: UInt32 = 0
    private var leases: [UUID:(Set<UUID>,TimeInterval)] = [:]
    private(set) var relayed = 0
    init(node: UUID) { self.node = node }
    func observeGateway(_ gateway: UUID, destinations: Set<UUID>) {
        guard gateway != node, leases.count < 7 || leases[gateway] != nil else { return }
        leases[gateway] = (Set(destinations.prefix(7)),clock())
    }
    func gateway(for destination: UUID) -> UUID {
        leases = leases.filter { clock() - $0.value.1 < 6 }
        return (leases.filter { $0.value.0.contains(destination) }.map(\.key) + [node])
            .min { $0.uuidString.lowercased() < $1.uuidString.lowercased() }!
    }
    func originate(kind: UInt8, payload: Data) {
        if kind == 2 { audioSequence &+= 1 } else { controlSequence &+= 1 }
        let p = HybridPacket(origin:node,previous:node,sequence:kind == 2 ? audioSequence : controlSequence,
            timestamp:UInt64(Date().timeIntervalSince1970 * 1000),kind:kind,payload:payload)
        _ = remember(p.id); send(p, excluding:nil)
    }
    func receive(from: UUID, data: Data, internet: Bool = false) {
        guard let p = HybridPacket.decode(data), p.previous == from, p.origin != node,
              !internet || (p.internetHops == 1 && internetPeers().contains(from)), remember(p.id) else { return }
        if p.kind == 3, p.internetHops == 0,
           let json = try? JSONSerialization.jsonObject(with:p.payload) as? [String:Any],
           let ids = json["gateways"] as? [String] {
            observeGateway(p.origin,destinations:Set(ids.prefix(7).compactMap(UUID.init(uuidString:))))
        }
        deliver(p)
        guard p.ttl > 0 else { return }
        var f = p; f.ttl -= 1; f.hops += 1; f.previous = node
        relayed += 1; send(f,excluding:from)
    }
    private func send(_ p: HybridPacket, excluding: UUID?) {
        localSend(excluding,p.encode())
        guard p.internetHops == 0 else { return }
        var uploaded = p; uploaded.internetHops = 1
        for destination in internetPeers() where destination != p.origin {
            if p.origin == node || gateway(for:destination) == node { internetSend(destination,uploaded.encode()) }
        }
    }
    private func remember(_ id: UUID) -> Bool {
        guard seen.insert(id).inserted else { return false }
        order.append(id)
        if order.count > 8192 { seen.remove(order.removeFirst()) }
        return true
    }
}
