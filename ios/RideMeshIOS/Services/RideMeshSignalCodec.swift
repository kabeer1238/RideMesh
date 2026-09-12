import Foundation

enum RideSignalType: UInt8 {
    case offer = 1
    case answer = 2
    case candidate = 3
    case bye = 4
}

struct RideSignalPacket {
    let from: UUID
    let to: UUID
    let type: RideSignalType
    var payload: String = ""
    var mid: String = ""
    var line: Int32 = -1
}

struct RidePresencePacket {
    let origin: UUID
    let timestampMs: Int64
    let riderName: String
    let deviceName: String
}

enum RideMeshSignalCodec {
    static let broadcastID = UUID(uuid: (0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0))
    private static let signalMagic: UInt32 = 0x524D5334 // RMS4
    private static let signalVersion: UInt8 = 1
    private static let signalFixedBytes = 48
    private static let maxSignalBytes = 128_000
    private static let maxMidBytes = 512
    private static let maxRiderNameBytes = 48
    private static let maxDeviceNameBytes = 64
    private static let locationMagic: UInt32 = 0x524D4C31 // RML1
    private static let locationVersion: UInt8 = 1
    private static let maxLocationNameBytes = 48
    private static let maxLocationPhoneBytes = 32

    static func encodeSignal(_ packet: RideSignalPacket) -> Data {
        let payload = Data(packet.payload.utf8)
        let mid = Data(packet.mid.utf8.prefix(maxMidBytes))
        var out = Data()
        out.appendBE(signalMagic)
        out.append(signalVersion)
        out.append(packet.type.rawValue)
        out.appendUUID(packet.from)
        out.appendUUID(packet.to)
        out.appendBE(packet.line)
        out.appendBE(Int32(payload.count))
        out.appendBE(UInt16(mid.count))
        out.append(payload)
        out.append(mid)
        return out
    }

    static func decodeSignal(_ data: Data) -> RideSignalPacket? {
        guard data.count >= signalFixedBytes, data.count <= maxSignalBytes else { return nil }
        var cursor = DataCursor(data)
        guard cursor.readUInt32() == signalMagic,
              cursor.readUInt8() == signalVersion,
              let typeRaw = cursor.readUInt8(),
              let type = RideSignalType(rawValue: typeRaw),
              let from = cursor.readUUID(),
              let to = cursor.readUUID(),
              let line = cursor.readInt32(),
              let payloadLengthRaw = cursor.readInt32(),
              let midLengthRaw = cursor.readUInt16()
        else { return nil }

        let payloadLength = Int(payloadLengthRaw)
        let midLength = Int(midLengthRaw)
        guard payloadLength >= 0, midLength >= 0, midLength <= maxMidBytes,
              cursor.remaining >= payloadLength + midLength,
              let payloadData = cursor.readData(count: payloadLength),
              let midData = cursor.readData(count: midLength)
        else { return nil }

        return RideSignalPacket(
            from: from,
            to: to,
            type: type,
            payload: String(data: payloadData, encoding: .utf8) ?? "",
            mid: String(data: midData, encoding: .utf8) ?? "",
            line: line
        )
    }

    static func encodePresence(_ packet: RidePresencePacket) -> Data {
        let rider = Data(packet.riderName.utf8.prefix(maxRiderNameBytes))
        let device = Data(packet.deviceName.utf8.prefix(maxDeviceNameBytes))
        var out = Data()
        out.appendUUID(packet.origin)
        out.appendBE(packet.timestampMs)
        out.append(UInt8(rider.count))
        out.append(rider)
        out.append(UInt8(device.count))
        out.append(device)
        return out
    }

    static func decodePresence(_ data: Data) -> RidePresencePacket? {
        var cursor = DataCursor(data)
        guard let origin = cursor.readUUID(),
              let timestamp = cursor.readInt64(),
              let riderCount = cursor.readUInt8(),
              let riderData = cursor.readData(count: Int(riderCount)),
              let deviceCount = cursor.readUInt8(),
              let deviceData = cursor.readData(count: Int(deviceCount))
        else { return nil }

        return RidePresencePacket(
            origin: origin,
            timestampMs: timestamp,
            riderName: String(data: riderData, encoding: .utf8) ?? "",
            deviceName: String(data: deviceData, encoding: .utf8) ?? ""
        )
    }


    // Separate lightweight map packet. Voice media never shares this payload/path.
    // Cross-platform wire format (RML1): magic/version, UUID, timestamp, lat/lon,
    // speed, heading, quality, short UTF-8 display name and an optional phone tail.
    // The phone tail matches the Android Beta5.x extension: one length byte + UTF-8.
    static func encodeLocation(_ packet: RiderLocationPacket) -> Data {
        let name = Data(packet.displayName.utf8.prefix(maxLocationNameBytes))
        let phone = Data((packet.phoneNumber ?? "").utf8.prefix(maxLocationPhoneBytes))
        var out = Data()
        out.appendBE(locationMagic)
        out.append(locationVersion)
        out.appendUUID(packet.riderId)
        out.appendBE(Int64(packet.timestamp.timeIntervalSince1970 * 1000))
        out.appendBEDouble(packet.latitude)
        out.appendBEDouble(packet.longitude)
        out.appendBEFloat(Float(packet.speedKmh))
        out.appendBEFloat(Float(packet.heading))
        // Extended RML1 follows Android's established 1-based quality values so
        // current Android map builds read iPhone quality correctly.
        out.append(packet.connectionQuality.androidWireValue)
        out.append(UInt8(name.count))
        out.append(name)
        out.append(UInt8(phone.count))
        out.append(phone)
        return out
    }

    static func decodeLocation(_ data: Data) -> RiderLocationPacket? {
        var cursor = DataCursor(data)
        guard cursor.readUInt32() == locationMagic,
              cursor.readUInt8() == locationVersion,
              let riderID = cursor.readUUID(),
              let timestampMs = cursor.readInt64(),
              let latitude = cursor.readDouble(),
              let longitude = cursor.readDouble(),
              let speed = cursor.readFloat(),
              let heading = cursor.readFloat(),
              let qualityRaw = cursor.readUInt8(),
              let nameLength = cursor.readUInt8(),
              Int(nameLength) <= maxLocationNameBytes,
              let nameData = cursor.readData(count: Int(nameLength))
        else { return nil }

        guard (-90...90).contains(latitude), (-180...180).contains(longitude),
              latitude.isFinite, longitude.isFinite else { return nil }

        // Canonical iOS vc23/vc24 packets ended after the display name and used
        // 0-based quality. Android Beta5.x extended RML1 appends phone length +
        // phone bytes and uses 1-based quality. Accept both representations.
        var phoneNumber: String?
        let quality: RiderConnectionQuality
        if cursor.remaining > 0, let phoneLength = cursor.readUInt8(),
           Int(phoneLength) <= maxLocationPhoneBytes,
           let phoneData = cursor.readData(count: Int(phoneLength)) {
            let decoded = String(data: phoneData, encoding: .utf8) ?? ""
            phoneNumber = decoded.isEmpty ? nil : decoded
            quality = RiderConnectionQuality(androidWireValue: qualityRaw)
        } else {
            phoneNumber = nil
            quality = RiderConnectionQuality(wireValue: qualityRaw)
        }

        return RiderLocationPacket(
            riderId: riderID,
            displayName: String(data: nameData, encoding: .utf8) ?? "Rider",
            latitude: latitude,
            longitude: longitude,
            speedKmh: max(0, Double(speed)),
            heading: Double(heading),
            timestamp: Date(timeIntervalSince1970: Double(timestampMs) / 1000),
            connectionQuality: quality,
            phoneNumber: phoneNumber
        )
    }
}

private struct DataCursor {
    let data: Data
    var offset = 0
    var remaining: Int { data.count - offset }

    init(_ data: Data) { self.data = data }

    mutating func readUInt8() -> UInt8? {
        guard remaining >= 1 else { return nil }
        defer { offset += 1 }
        return data[data.index(data.startIndex, offsetBy: offset)]
    }

    mutating func readUInt16() -> UInt16? {
        guard let d = readData(count: 2) else { return nil }
        return d.withUnsafeBytes { raw in UInt16(bigEndian: raw.loadUnaligned(as: UInt16.self)) }
    }

    mutating func readUInt32() -> UInt32? {
        guard let d = readData(count: 4) else { return nil }
        return d.withUnsafeBytes { raw in UInt32(bigEndian: raw.loadUnaligned(as: UInt32.self)) }
    }

    mutating func readInt32() -> Int32? {
        guard let value = readUInt32() else { return nil }
        return Int32(bitPattern: value)
    }

    mutating func readInt64() -> Int64? {
        guard let d = readData(count: 8) else { return nil }
        let value = d.withUnsafeBytes { raw in UInt64(bigEndian: raw.loadUnaligned(as: UInt64.self)) }
        return Int64(bitPattern: value)
    }

    mutating func readDouble() -> Double? {
        guard let d = readData(count: 8) else { return nil }
        let bits = d.withUnsafeBytes { raw in UInt64(bigEndian: raw.loadUnaligned(as: UInt64.self)) }
        return Double(bitPattern: bits)
    }

    mutating func readFloat() -> Float? {
        guard let d = readData(count: 4) else { return nil }
        let bits = d.withUnsafeBytes { raw in UInt32(bigEndian: raw.loadUnaligned(as: UInt32.self)) }
        return Float(bitPattern: bits)
    }

    mutating func readUUID() -> UUID? {
        guard let bytes = readData(count: 16) else { return nil }
        var value: uuid_t = (0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0)
        _ = withUnsafeMutableBytes(of: &value) { dest in bytes.copyBytes(to: dest) }
        return UUID(uuid: value)
    }

    mutating func readData(count: Int) -> Data? {
        guard count >= 0, remaining >= count else { return nil }
        let start = data.index(data.startIndex, offsetBy: offset)
        let end = data.index(start, offsetBy: count)
        offset += count
        return data[start..<end]
    }
}

private extension Data {
    mutating func appendUUID(_ uuid: UUID) {
        var tuple = uuid.uuid
        Swift.withUnsafeBytes(of: &tuple) { append(contentsOf: $0) }
    }

    mutating func appendBE<T: FixedWidthInteger>(_ value: T) {
        var be = value.bigEndian
        Swift.withUnsafeBytes(of: &be) { append(contentsOf: $0) }
    }

    mutating func appendBEDouble(_ value: Double) {
        appendBE(value.bitPattern)
    }

    mutating func appendBEFloat(_ value: Float) {
        appendBE(value.bitPattern)
    }
}
