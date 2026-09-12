import Foundation

/// Byte-for-byte contract shared with Android WifiAwareWireProtocol.kt.
enum RideMeshOfflineWireProtocol {
    static let serviceName = "_ridemesh._tcp"
    static let tcpPort: UInt16 = 49355
    static let protocolVersion = 1
    static let maxFrameBytes = 256 * 1024

    enum FrameType: UInt8 { case hello = 1, data = 2, ping = 3, pong = 4 }

    struct Identity: Equatable, Sendable {
        let nodeId: String
        let rideToken: String
        let riderName: String
    }

    static func rideToken(for rideCode: String) -> String {
        // SHA-256 is supplied by CryptoKit on iOS 13+.
        let normalized = rideCode.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        return SHA256Bridge.hexPrefix64(Data(normalized.utf8))
    }

    static func encodeIdentity(_ identity: Identity) -> Data {
        Data("RMESH1|1|\(safe(identity.nodeId, 48))|\(safe(identity.rideToken, 32))|\(safe(identity.riderName, 32))".utf8)
    }

    static func decodeIdentity(_ data: Data) -> Identity? {
        guard let text = String(data: data, encoding: .utf8) else { return nil }
        let p = text.split(separator: "|", maxSplits: 4, omittingEmptySubsequences: false).map(String.init)
        guard p.count == 5, p[0] == "RMESH1", p[1] == "1", !p[2].isEmpty, !p[3].isEmpty else { return nil }
        return Identity(nodeId: p[2], rideToken: p[3], riderName: p[4])
    }

    static func frame(_ type: FrameType, body: Data = Data()) -> Data {
        precondition(body.count + 1 <= maxFrameBytes)
        var out = Data()
        var length = UInt32(body.count + 1).bigEndian
        withUnsafeBytes(of: &length) { out.append(contentsOf: $0) }
        out.append(type.rawValue)
        out.append(body)
        return out
    }

    static func encodeInt64(_ value: Int64) -> Data {
        var v = UInt64(bitPattern: value).bigEndian
        return withUnsafeBytes(of: &v) { Data($0) }
    }

    static func decodeInt64(_ data: Data) -> Int64? {
        guard data.count == 8 else { return nil }
        let u = data.reduce(UInt64(0)) { ($0 << 8) | UInt64($1) }
        return Int64(bitPattern: u)
    }

    private static func safe(_ value: String, _ max: Int) -> String {
        String(value.replacingOccurrences(of: "|", with: "-")
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines).prefix(max))
    }
}

private enum SHA256Bridge {
    static func hexPrefix64(_ data: Data) -> String {
        #if canImport(CryptoKit)
        return CryptoKitSHA256.hexPrefix64(data)
        #else
        fatalError("CryptoKit is required")
        #endif
    }
}

#if canImport(CryptoKit)
import CryptoKit
private enum CryptoKitSHA256 {
    static func hexPrefix64(_ data: Data) -> String {
        SHA256.hash(data: data).prefix(8).map { String(format: "%02x", $0) }.joined()
    }
}
#endif
