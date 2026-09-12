import Foundation

enum RideMeshScreen {
    case profile
    case home
    case setup
    case active
}



enum RideMainTab: String, CaseIterable, Identifiable {
    case ride = "RIDE"
    case map = "MAP"
    case riders = "RIDERS"
    case settings = "SETTINGS"

    var id: String { rawValue }

    var symbol: String {
        switch self {
        case .ride: return "waveform"
        case .map: return "map.fill"
        case .riders: return "person.3.fill"
        case .settings: return "gearshape.fill"
        }
    }
}

struct RiderLocationPacket: Hashable {
    let riderId: UUID
    var displayName: String
    var latitude: Double
    var longitude: Double
    var speedKmh: Double
    var heading: Double
    var timestamp: Date
    var connectionQuality: RiderConnectionQuality
    var phoneNumber: String? = nil
}

struct RiderMapPoint: Identifiable, Hashable {
    let id: UUID
    var displayName: String
    var latitude: Double
    var longitude: Double
    var speedKmh: Double
    var heading: Double
    var timestamp: Date
    var connectionQuality: RiderConnectionQuality
    var isYou: Bool
    var distanceMeters: Double?
    var phoneNumber: String? = nil

    var isStale: Bool { Date().timeIntervalSince(timestamp) > 8 }

    var distanceText: String {
        guard let distanceMeters else { return "Distance unavailable" }
        if distanceMeters < 1000 { return "\(Int(distanceMeters.rounded())) m from you" }
        return String(format: "%.1f km from you", distanceMeters / 1000)
    }

    var speedText: String { "\(Int(max(0, speedKmh).rounded())) km/h" }
}

enum RideSetupMode: String {
    case create = "CREATE RIDE"
    case join = "JOIN RIDE"

    var lobbyTitle: String { "RIDE LOBBY" }
    var helperText: String {
        switch self {
        case .create: return "Create a code and invite your riding group."
        case .join: return "Enter the code shared by your ride host."
        }
    }
}


enum RiderConnectionQuality: String, CaseIterable, Hashable {
    case excellent = "EXCELLENT"
    case good = "GOOD"
    case poor = "POOR"
    case reconnecting = "RECONNECTING…"

    var bars: Int {
        switch self {
        case .excellent: return 4
        case .good: return 3
        case .poor: return 2
        case .reconnecting: return 1
        }
    }

    var wireValue: UInt8 {
        switch self {
        case .excellent: return 0
        case .good: return 1
        case .poor: return 2
        case .reconnecting: return 3
        }
    }

    init(wireValue: UInt8) {
        switch wireValue {
        case 0: self = .excellent
        case 1: self = .good
        case 2: self = .poor
        default: self = .reconnecting
        }
    }

    var androidWireValue: UInt8 {
        switch self {
        case .excellent: return 1
        case .good: return 2
        case .poor: return 3
        case .reconnecting: return 4
        }
    }

    init(androidWireValue: UInt8) {
        switch androidWireValue {
        case 1: self = .excellent
        case 2: self = .good
        case 3: self = .poor
        default: self = .reconnecting
        }
    }
}

enum RideAudioRoute: String, CaseIterable, Identifiable {
    case automatic = "AUTO"
    case phone = "PHONE"
    case helmet = "HELMET"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .automatic: return "Auto — helmet if connected, otherwise phone"
        case .phone: return "Phone speaker + microphone"
        case .helmet: return "Bluetooth helmet / headset"
        }
    }

    var dialogTitle: String {
        switch self {
        case .automatic: return "AUTOMATIC"
        case .phone: return "PHONE AUDIO"
        case .helmet: return "BLUETOOTH HELMET"
        }
    }

    var shortTitle: String {
        switch self {
        case .automatic: return "AUTO"
        case .phone: return "PHONE"
        case .helmet: return "HELMET"
        }
    }
}

struct RiderPeer: Identifiable, Hashable {
    let id: UUID
    var riderName: String
    var deviceName: String
    var lastSeen: Date
    var connected: Bool
    var qualityBars: Int
    var connectionQuality: RiderConnectionQuality = .reconnecting

    var displayName: String {
        let cleaned = riderName.trimmingCharacters(in: .whitespacesAndNewlines)
        if !cleaned.isEmpty { return cleaned }
        let device = deviceName.trimmingCharacters(in: .whitespacesAndNewlines)
        if !device.isEmpty { return device }
        return "Rider \(id.uuidString.prefix(4).uppercased())"
    }
}

// Engineering-only state. Normal rider UI must translate this into simple
// Connection / Voice / Headset / Riders / Audio Quality language.
struct RideMeshDiagnostics {
    var signalingConnected = false
    var knownRiders = 0
    var voicePeersConnected = 0
    var offersSent = 0
    var answersSent = 0
    var candidatesSent = 0
    var reconnects = 0
    var connectionRecoveries = 0
    var remoteSpeechActive = false
    var localSpeechActive = false
    var smartDuckingActive = false
    var opusDtxEnabled = true
    var motorcycleNoiseGuardEnabled = true
    var adaptiveOpusBitrateKbps = 24
    var lastError = ""
    var codec = "Opus / WebRTC"
    var turnConfigured = false
}
