import CoreLocation
import Foundation

@MainActor
final class RideLocationService: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published private(set) var currentLocation: CLLocation?
    @Published private(set) var headingDegrees: Double = 0
    @Published private(set) var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published private(set) var isSharing = false
    @Published private(set) var lastError = ""

    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.activityType = .automotiveNavigation
        manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
        manager.distanceFilter = 3
        manager.headingFilter = 8
        manager.pausesLocationUpdatesAutomatically = true
        authorizationStatus = manager.authorizationStatus
    }

    var speedKmh: Double {
        guard let location = currentLocation, location.speed >= 0 else { return 0 }
        return location.speed * 3.6
    }

    var effectiveHeading: Double {
        if let course = currentLocation?.course, course >= 0 { return course }
        return headingDegrees
    }

    var isAuthorized: Bool {
        authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways
    }

    func startSharing() {
        authorizationStatus = manager.authorizationStatus
        switch authorizationStatus {
        case .notDetermined:
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            beginUpdates()
        case .denied, .restricted:
            isSharing = false
            lastError = "Location permission is required to appear on the Live Rider Map."
        @unknown default:
            isSharing = false
        }
    }

    func stopSharing() {
        manager.stopUpdatingLocation()
        manager.stopUpdatingHeading()
        isSharing = false
        currentLocation = nil
        headingDegrees = 0
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        authorizationStatus = manager.authorizationStatus
        switch authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways:
            if !isSharing { beginUpdates() }
        case .denied, .restricted:
            isSharing = false
            lastError = "Location sharing is off. Enable location access for RideMesh to use the Live Rider Map."
        default:
            break
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last,
              location.horizontalAccuracy >= 0,
              location.horizontalAccuracy <= 120,
              abs(location.timestamp.timeIntervalSinceNow) < 15 else { return }
        currentLocation = location
        lastError = ""
    }

    func locationManager(_ manager: CLLocationManager, didUpdateHeading newHeading: CLHeading) {
        let value = newHeading.trueHeading >= 0 ? newHeading.trueHeading : newHeading.magneticHeading
        if value >= 0 { headingDegrees = value }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        let ns = error as NSError
        if ns.domain == kCLErrorDomain, ns.code == CLError.locationUnknown.rawValue { return }
        lastError = error.localizedDescription
    }

    private func beginUpdates() {
        guard CLLocationManager.locationServicesEnabled() else {
            isSharing = false
            lastError = "Location Services are disabled on this iPhone."
            return
        }
        // Sharing exists only during an explicitly active RideMesh ride. The audio
        // session already keeps the user-initiated ride alive; background location
        // is enabled only for that same session and stops immediately at END RIDE.
        manager.allowsBackgroundLocationUpdates = true
        manager.showsBackgroundLocationIndicator = true
        manager.startUpdatingLocation()
        if CLLocationManager.headingAvailable() { manager.startUpdatingHeading() }
        isSharing = true
    }
}
