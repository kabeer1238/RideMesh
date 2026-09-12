import Foundation
import Network

@MainActor
final class RideNetworkMonitor: ObservableObject {
    @Published private(set) var isOnline = false
    @Published private(set) var interfaceText = "Checking…"

    private let monitor = NWPathMonitor()
    private let queue = DispatchQueue(label: "RideMesh.NetworkMonitor")

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            Task { @MainActor in
                guard let self else { return }
                self.isOnline = path.status == .satisfied
                if path.status != .satisfied {
                    self.interfaceText = "Offline"
                } else if path.usesInterfaceType(.wifi) {
                    self.interfaceText = "Wi‑Fi"
                } else if path.usesInterfaceType(.cellular) {
                    self.interfaceText = "Mobile Data"
                } else if path.usesInterfaceType(.wiredEthernet) {
                    self.interfaceText = "Ethernet"
                } else {
                    self.interfaceText = "Internet"
                }
            }
        }
        monitor.start(queue: queue)
    }

    deinit {
        monitor.cancel()
    }
}
