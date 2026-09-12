import Combine
import CoreLocation
import Foundation
import UIKit

@MainActor
final class RideMeshViewModel: ObservableObject {
    @Published var screen: RideMeshScreen
    @Published var setupMode: RideSetupMode = .create
    @Published var riderName: String
    @Published var rideCode: String
    @Published var phoneNumber: String
    @Published var audioRoute: RideAudioRoute
    @Published var batterySaver: Bool
    @Published private(set) var micMuted = false
    @Published private(set) var isRideActive = false
    @Published private(set) var statusMessage = "READY"
    @Published private(set) var errorMessage: String?
    @Published var activeTab: RideMainTab = .ride

    @Published var showSettings = false
    @Published var showQR = false
    @Published var showScanner = false
    @Published var showRiders = false
    @Published var showInvite = false
    @Published var showAudioRoutes = false
    @Published var showDiagnostics = false
    @Published var showOfflineDiscovery = false
    @Published var confirmEndRide = false

    let network = RideNetworkMonitor()
    let audio = AudioSessionManager()
    let voice = WebRTCVoiceService()
    lazy var hybrid = HybridSession(voice:voice)
    @Published var hybridEnabled = UserDefaults.standard.object(forKey:"hybrid_enabled") as? Bool ?? true
    let battery = RideBatteryMonitor()
    let location = RideLocationService()

    private let defaults = UserDefaults.standard
    private var cancellables = Set<AnyCancellable>()
    private var locationPublishTask: Task<Void, Never>?

    init() {
        let storedName = UserDefaults.standard.string(forKey: "ridemesh_rider_name") ?? ""
        let configured = UserDefaults.standard.bool(forKey: "ridemesh_profile_configured") || !storedName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        let initialName = storedName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Rider" : storedName
        let initialRideCode = UserDefaults.standard.string(forKey: "ridemesh_ride_code") ?? "RM2815"
        let initialPhoneNumber = UserDefaults.standard.string(forKey: "ridemesh_phone_number") ?? ""
        let initialAudioRoute = RideAudioRoute(
            rawValue: UserDefaults.standard.string(forKey: "ridemesh_audio_route") ?? "AUTO"
        ) ?? .automatic
        let initialBatterySaver = UserDefaults.standard.object(forKey: "ridemesh_battery_saver") as? Bool ?? true

        riderName = initialName
        rideCode = initialRideCode
        phoneNumber = initialPhoneNumber
        audioRoute = initialAudioRoute
        batterySaver = initialBatterySaver
        screen = configured ? .home : .profile

        audio.$isInterrupted
            .removeDuplicates()
            .sink { [weak self] interrupted in
                self?.voice.setSystemInterrupted(interrupted)
                if self?.hybridEnabled == true { self?.hybrid.interrupted(interrupted) }
            }
            .store(in: &cancellables)

        voice.$smartDuckingActive
            .removeDuplicates()
            .sink { [weak self] active in
                self?.audio.setSpeechDuckingActive(active)
            }
            .store(in: &cancellables)

        voice.$statusText
            .sink { [weak self] in if self?.hybridEnabled == false { self?.statusMessage = $0 } }
            .store(in: &cancellables)

        Publishers.CombineLatest(network.$isOnline, network.$interfaceText)
            .debounce(for: .milliseconds(250), scheduler: RunLoop.main)
            .removeDuplicates { lhs, rhs in lhs.0 == rhs.0 && lhs.1 == rhs.1 }
            .sink { [weak self] isOnline, interface in
                guard let self, self.isRideActive else { return }
                self.voice.handleNetworkPathChange(isOnline: isOnline, interface: interface)
                if isOnline {
                    self.audio.ensureRideAudioActive()
                    self.voice.ensureAudioCaptureRunning()
                }
            }
            .store(in: &cancellables)

        hybrid.$summary.sink { [weak self] text in
            if self?.hybridEnabled == true { self?.statusMessage = text }
        }.store(in:&cancellables)

        [hybrid.objectWillChange.eraseToAnyPublisher(), network.objectWillChange.eraseToAnyPublisher(),
         audio.objectWillChange.eraseToAnyPublisher(),
         voice.objectWillChange.eraseToAnyPublisher(),
         battery.objectWillChange.eraseToAnyPublisher(),
         location.objectWillChange.eraseToAnyPublisher()]
            .publisher
            .flatMap { $0 }
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &cancellables)
    }

    var peers: [RiderPeer] {
        guard hybridEnabled else { return voice.peers }
        return hybrid.riders.map { RiderPeer(id:$0.key,riderName:$0.value,deviceName:"Hybrid rider",lastSeen:Date(),connected:true,qualityBars:0) }
            .sorted { $0.displayName < $1.displayName }
    }
    var connectedVoicePeers: Int { hybridEnabled ? hybrid.riders.count : voice.diagnostics.voicePeersConnected }
    var totalConnectedRiders: Int { max(1, connectedVoicePeers + 1) }

    var groupRiderCount: Int { max(1, peers.count + 1) }
    var isLocationSharing: Bool { isRideActive && location.isSharing && voice.diagnostics.signalingConnected }

    func riderMapPoints(now: Date = Date()) -> [RiderMapPoint] {
        var points: [RiderMapPoint] = []
        let localLocation = location.currentLocation

        if let localLocation {
            points.append(RiderMapPoint(
                id: voice.localRiderID,
                displayName: "YOU",
                latitude: localLocation.coordinate.latitude,
                longitude: localLocation.coordinate.longitude,
                speedKmh: location.speedKmh,
                heading: location.effectiveHeading,
                timestamp: localLocation.timestamp,
                connectionQuality: localConnectionQuality,
                isYou: true,
                distanceMeters: 0,
                phoneNumber: sanitizedPhoneNumber.isEmpty ? nil : sanitizedPhoneNumber
            ))
        }

        for packet in voice.riderLocations.values {
            let remoteLocation = CLLocation(latitude: packet.latitude, longitude: packet.longitude)
            let distance = localLocation.map { $0.distance(from: remoteLocation) }
            let peer = peers.first(where: { $0.id == packet.riderId })
            let quality: RiderConnectionQuality
            if now.timeIntervalSince(packet.timestamp) > 12 {
                quality = .reconnecting
            } else {
                quality = peer.map { $0.connected ? $0.connectionQuality : .reconnecting } ?? packet.connectionQuality
            }
            points.append(RiderMapPoint(
                id: packet.riderId,
                displayName: peer?.displayName ?? packet.displayName,
                latitude: packet.latitude,
                longitude: packet.longitude,
                speedKmh: packet.speedKmh,
                heading: packet.heading,
                timestamp: packet.timestamp,
                connectionQuality: quality,
                isYou: false,
                distanceMeters: distance,
                phoneNumber: packet.phoneNumber
            ))
        }
        return points.sorted { lhs, rhs in
            if lhs.isYou != rhs.isYou { return lhs.isYou }
            return lhs.displayName.localizedCaseInsensitiveCompare(rhs.displayName) == .orderedAscending
        }
    }

    private var localConnectionQuality: RiderConnectionQuality {
        if !network.isOnline || !voice.diagnostics.signalingConnected { return .reconnecting }
        if peers.contains(where: { $0.connectionQuality == .poor }) { return .good }
        return connectedVoicePeers > 0 ? .excellent : .good
    }

    var connectionLabel: String {
        if hybridEnabled && isRideActive { return connectedVoicePeers > 0 ? "HYBRID CONNECTED" : "FINDING RIDERS" }
        if !network.isOnline { return "WAITING FOR INTERNET" }
        if voice.diagnostics.signalingConnected { return "CONNECTED" }
        return isRideActive ? "RECONNECTING…" : "READY"
    }

    var inviteURL: URL {
        var components = URLComponents()
        components.scheme = "ridemesh"
        components.host = "join"
        components.queryItems = [URLQueryItem(name: "ride", value: normalizedRideCode)]
        return components.url ?? URL(string: "ridemesh://join?ride=RM2815")!
    }

    var normalizedRideCode: String { RideMeshSignalingService.sanitizeRideCode(rideCode) }

    func saveRiderProfile() {
        let clean = riderName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard clean.count >= 2 else {
            errorMessage = "Enter the rider name you want your group to see."
            return
        }
        riderName = String(clean.prefix(18))
        defaults.set(true, forKey: "ridemesh_profile_configured")
        persist()
        screen = .home
    }

    func editRiderProfile() {
        showSettings = false
        screen = .profile
    }

    func createRide() {
        setupMode = .create
        rideCode = generateRideCode()
        screen = .setup
        persist()
    }

    func joinRide() {
        setupMode = .join
        screen = .setup
    }

    func returnHome() {
        screen = .home
    }

    func startRide() {
        guard !isRideActive else { return }
        let code = normalizedRideCode
        guard code.count >= 5 else {
            errorMessage = "Ride code must be at least 5 characters."
            return
        }

        Task {
            let allowed = await audio.requestMicrophonePermission()
            guard allowed else {
                errorMessage = "Microphone permission is required for RideMesh voice."
                return
            }

            do {
                try audio.configureForRide(route: audioRoute)
            } catch {
                errorMessage = error.localizedDescription
                return
            }

            let cleanName = riderName.trimmingCharacters(in: .whitespacesAndNewlines)
            riderName = cleanName.isEmpty ? "Rider" : String(cleanName.prefix(18))
            phoneNumber = sanitizedPhoneNumber
            rideCode = code
            persist()
            micMuted = false
            voice.setMuted(false)
            voice.start(
                rideCode: rideCode,
                riderName: riderName,
                deviceName: UIDevice.current.model,
                batterySmart: batterySaver, hybrid:hybridEnabled
            )
            if hybridEnabled { hybrid.start(name:riderName,code:rideCode) }
            battery.startSession()
            isRideActive = true
            activeTab = .ride
            location.startSharing()
            startLocationPublishing()
            screen = .active
        }
    }

    func requestEndRide() {
        confirmEndRide = true
    }

    func stopRide() {
        // vc17 principle: an explicit END RIDE releases every active-ride resource.
        hybrid.stop()
        voice.stop()
        audio.deactivate()
        battery.stopSession()
        locationPublishTask?.cancel()
        locationPublishTask = nil
        location.stopSharing()
        micMuted = false
        isRideActive = false
        activeTab = .ride
        confirmEndRide = false
        screen = .home
    }

    func toggleMute() {
        micMuted.toggle()
        voice.setMuted(micMuted)
        hybrid.mute(micMuted)
    }

    func handleAppBecameActive() {
        audio.refreshRouteState()
        guard isRideActive else { return }

        // Safety net for interruptions that do not deliver a matching ended event.
        // The ride/peers remain alive; we only reassert audio ownership and capture.
        audio.ensureRideAudioActive()
        voice.ensureAudioCaptureRunning()
        location.startSharing()
        if locationPublishTask == nil { startLocationPublishing() }
    }

    func chooseAudioRoute(_ route: RideAudioRoute) {
        audioRoute = route
        persist()
        if isRideActive {
            do {
                try audio.select(route: route)
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    func acceptScannedCode(_ raw: String) {
        guard let code = Self.parseRideInvite(raw) else {
            errorMessage = "That QR code is not a RideMesh invite."
            return
        }
        rideCode = code
        setupMode = .join
        screen = .setup
        showScanner = false
        persist()
    }

    func handleOpenURL(_ url: URL) {
        guard let code = Self.parseRideInvite(url.absoluteString) else { return }
        rideCode = code
        setupMode = .join
        screen = .setup
        persist()
    }

    func selectActiveTab(_ tab: RideMainTab) {
        activeTab = tab
    }

    func navigateExternally(to rider: RiderMapPoint) {
        guard !rider.isYou else { return }
        let lat = rider.latitude
        let lon = rider.longitude
        if let google = URL(string: "comgooglemaps://?daddr=\(lat),\(lon)&directionsmode=driving"),
           UIApplication.shared.canOpenURL(google) {
            UIApplication.shared.open(google)
            return
        }
        if let web = URL(string: "https://www.google.com/maps/dir/?api=1&destination=\(lat),\(lon)&travelmode=driving") {
            UIApplication.shared.open(web)
        }
    }

    func callRider(_ rider: RiderMapPoint) {
        guard let number = callablePhoneNumber(for: rider),
              let url = URL(string: "tel:\(number)") else {
            errorMessage = "No phone number was shared by this rider."
            return
        }
        UIApplication.shared.open(url)
    }

    func callRiderViaWhatsApp(_ rider: RiderMapPoint) {
        guard let digits = whatsAppPhoneNumber(for: rider) else {
            errorMessage = "No phone number was shared by this rider."
            return
        }

        // Rider-safety rule: RideMesh never auto-places a call. For the
        // WhatsApp call option we open that rider's WhatsApp conversation; the
        // user then taps WhatsApp's call button explicitly.
        if let chat = URL(string: "whatsapp://send?phone=\(digits)"), UIApplication.shared.canOpenURL(chat) {
            UIApplication.shared.open(chat)
            return
        }
        if let web = URL(string: "https://wa.me/\(digits)") {
            UIApplication.shared.open(web)
        }
    }

    func messageRider(_ rider: RiderMapPoint) {
        guard let number = callablePhoneNumber(for: rider),
              let url = URL(string: "sms:\(number)") else {
            errorMessage = "No phone number was shared by this rider."
            return
        }
        UIApplication.shared.open(url)
    }

    func messageRiderViaWhatsApp(_ rider: RiderMapPoint) {
        guard let digits = whatsAppPhoneNumber(for: rider) else {
            errorMessage = "No phone number was shared by this rider."
            return
        }
        if let app = URL(string: "whatsapp://send?phone=\(digits)"), UIApplication.shared.canOpenURL(app) {
            UIApplication.shared.open(app)
            return
        }
        if let web = URL(string: "https://wa.me/\(digits)") {
            UIApplication.shared.open(web)
        }
    }

    private func callablePhoneNumber(for rider: RiderMapPoint) -> String? {
        guard let raw = rider.phoneNumber else { return nil }
        let clean = Self.sanitizePhone(raw)
        return clean.isEmpty ? nil : clean
    }

    private func whatsAppPhoneNumber(for rider: RiderMapPoint) -> String? {
        guard let number = callablePhoneNumber(for: rider) else { return nil }
        let digits = number.filter(\.isNumber)
        return digits.isEmpty ? nil : digits
    }

    func dismissError() { errorMessage = nil }

    private func startLocationPublishing() {
        locationPublishTask?.cancel()
        locationPublishTask = Task { @MainActor [weak self] in
            guard let self else { return }
            while !Task.isCancelled, self.isRideActive {
                self.publishCurrentLocationIfPossible()
                let interval = self.locationPublishInterval()
                try? await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
            }
            self.locationPublishTask = nil
        }
    }

    private func publishCurrentLocationIfPossible() {
        guard isRideActive, network.isOnline, location.isSharing,
              let current = location.currentLocation,
              abs(current.timestamp.timeIntervalSinceNow) < 12 else { return }
        voice.publishLocation(RiderLocationPacket(
            riderId: voice.localRiderID,
            displayName: riderName,
            latitude: current.coordinate.latitude,
            longitude: current.coordinate.longitude,
            speedKmh: location.speedKmh,
            heading: location.effectiveHeading,
            timestamp: current.timestamp,
            connectionQuality: localConnectionQuality,
            phoneNumber: sanitizedPhoneNumber.isEmpty ? nil : sanitizedPhoneNumber
        ))
    }

    private func locationPublishInterval() -> TimeInterval {
        guard network.isOnline else { return 5.0 }
        let moving = location.speedKmh >= 3
        let lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
        let backgrounded = UIApplication.shared.applicationState != .active
        let weakNetwork = peers.contains { $0.connectionQuality == .poor || $0.connectionQuality == .reconnecting }

        // Voice/recovery always wins. Back off map telemetry before it can compete
        // with real-time audio on a weak link or while the phone is backgrounded.
        if weakNetwork { return 3.0 }
        if lowPower { return moving ? 2.5 : 8.0 }
        if backgrounded { return moving ? 2.0 : 6.0 }
        if !moving { return batterySaver ? 5.0 : 3.0 }
        return 1.0
    }

    func persist() {
        defaults.set(hybridEnabled,forKey:"hybrid_enabled")
        defaults.set(riderName, forKey: "ridemesh_rider_name")
        defaults.set(normalizedRideCode, forKey: "ridemesh_ride_code")
        defaults.set(sanitizedPhoneNumber, forKey: "ridemesh_phone_number")
        defaults.set(audioRoute.rawValue, forKey: "ridemesh_audio_route")
        defaults.set(batterySaver, forKey: "ridemesh_battery_saver")
    }

    var sanitizedPhoneNumber: String { Self.sanitizePhone(phoneNumber) }

    static func sanitizePhone(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        var output = ""
        for character in trimmed {
            if character.isNumber {
                output.append(character)
            } else if character == "+", output.isEmpty {
                output.append(character)
            }
            if output.count >= 20 { break }
        }
        return output
    }


    private func generateRideCode() -> String {
        "RM\(Int.random(in: 1000...9999))"
    }

    static func parseRideInvite(_ raw: String) -> String? {
        let plain = RideMeshSignalingService.sanitizeRideCode(raw)
        if !raw.contains("://"), plain.count >= 5 { return String(plain.prefix(12)) }

        guard let url = URL(string: raw),
              url.scheme?.lowercased() == "ridemesh",
              url.host?.lowercased() == "join",
              let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let ride = components.queryItems?.first(where: { $0.name == "ride" })?.value
        else { return nil }
        let code = RideMeshSignalingService.sanitizeRideCode(ride)
        return code.count >= 5 ? String(code.prefix(12)) : nil
    }
}
