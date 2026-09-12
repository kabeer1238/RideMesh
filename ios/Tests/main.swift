import Foundation

func check(_ condition: @autoclosure () -> Bool, _ text: String) {
    if !condition() { fatalError(text) }
}
let ids = (1...8).map { UUID(uuidString:String(format:"00000000-0000-0000-0000-%012d",$0))! }
let golden = HybridPacket(id:ids[0],origin:ids[1],previous:ids[2],sequence:7,timestamp:8,kind:2,payload:Data([1,2,3]))
let bytes = golden.encode()
check(bytes.count == 76,"73 byte header")
check(bytes.prefix(9) == Data([0x52,0x4d,0x45,0x31,2,2,0,6,0]),"Android header")
check(bytes[57..<61] == Data([0,0,0,7]),"sequence offset")
check(HybridPacket.decode(bytes)?.origin == ids[1],"UUID round trip")
check(HybridPacket.decode(Data(bytes.dropLast())) == nil,"truncation")
var invalid = bytes; invalid[6] = 2
check(HybridPacket.decode(invalid) == nil,"multiple internet crossings rejected")

var online = Set(0...4)
var edges = [(0,5),(1,5),(5,6),(6,7)]
var now:TimeInterval = 0
var played = Array(repeating:0,count:8)
var events: [(Int,Int,Data,Bool)] = []
let routers = ids.map { HybridRouter(node:$0) }
for i in 0..<8 {
    routers[i].clock = { now }
    routers[i].internetPeers = { online.contains(i) ? Set(online.filter { $0 != i }.map { ids[$0] }) : [] }
    routers[i].localSend = { excluded,data in
        for j in 0..<8 where ids[j] != excluded && edges.contains(where:{ ($0.0 == i && $0.1 == j) || ($0.0 == j && $0.1 == i) }) { events.append((i,j,data,false)) }
    }
    routers[i].internetSend = { peer,data in if let j = ids.firstIndex(of:peer) { events.append((i,j,data,true)) } }
    routers[i].deliver = { if $0.kind == 2 { played[i] += 1 } }
}
func speak(_ source:Int) {
    played = Array(repeating:0,count:8); events.removeAll()
    routers[source].originate(kind:2,payload:Data([1]))
    var index = 0
    while index < events.count {
        check(index < 300,"flood terminates")
        let e = events[index]; index += 1
        routers[e.1].receive(from:ids[e.0],data:e.2,internet:e.3)
    }
    for i in 0..<8 { check(played[i] == (i == source ? 0 : 1),"source \(source) receiver \(i)") }
}
for source in 0..<8 { speak(source) }
for i in [0,1,5,6,7] {
    for gateway in [0,1] { routers[i].observeGateway(ids[gateway],destinations:Set(online.filter { $0 != gateway }.map { ids[$0] })) }
}
for source in 0..<8 { speak(source) }
online.remove(0); now = 6.1
speak(7); speak(4)
online.removeAll(); edges = (0..<7).map { ($0,$0+1) }
for source in 0..<8 { speak(source) }
print("PASS: Android envelope, malformed packets, 5-online/3-offline all origins, dedup, gateway expiry, seven-hop chain")
