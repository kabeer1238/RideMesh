import SwiftUI
import WiFiAware
import DeviceDiscoveryUI

// This screen is deliberately limited to Apple system pairing and discovery.
// It validates the physical iPhone <-> Android Wi-Fi Aware link before RideMesh
// moves the WebRTC signalling and media transport onto that link.
@available(iOS 26.0, *)
enum RideMeshWiFiAware {
    static let serviceName = "_ridemesh._tcp"

    static var supported: Bool {
        WACapabilities.supportedFeatures.contains(.wifiAware)
    }
}

@available(iOS 26.0, *)
extension WAPublishableService {
    static var rideMesh: WAPublishableService {
        allServices[RideMeshWiFiAware.serviceName]!
    }
}

@available(iOS 26.0, *)
extension WASubscribableService {
    static var rideMesh: WASubscribableService {
        allServices[RideMeshWiFiAware.serviceName]!
    }
}

struct OfflineDiscoveryView: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            RideMeshBackground()
            VStack(spacing: 16) {
                RMModalHeader(title: "OFFLINE DISCOVERY") { dismiss() }
                if #available(iOS 26.0, *) {
                    WiFiAwareControls()
                } else {
                    unavailableCard
                }
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
        }
        .preferredColorScheme(.dark)
    }

    private var unavailableCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("IOS 26 REQUIRED")
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(RideMeshTheme.white)
            Text("Update this iPhone to iOS 26 or later to test direct RideMesh discovery.")
                .font(.system(size: 11))
                .foregroundStyle(RideMeshTheme.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .rmPanel(radius: 18)
    }
}

@available(iOS 26.0, *)
private struct WiFiAwareControls: View {
    @State private var selectedPeer = false

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 10) {
                Image(systemName: RideMeshWiFiAware.supported ? "antenna.radiowaves.left.and.right" : "exclamationmark.triangle.fill")
                    .foregroundStyle(RideMeshWiFiAware.supported ? RideMeshTheme.accent : RideMeshTheme.amber)
                Text(RideMeshWiFiAware.supported ? "WI-FI AWARE READY" : "WI-FI AWARE UNAVAILABLE")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(RideMeshTheme.white)
            }

            Text(RideMeshWiFiAware.supported
                 ? "Pair this iPhone and discover a nearby RideMesh device without mobile data, a router, or a hotspot."
                 : "This iPhone does not report Wi-Fi Aware support.")
                .font(.system(size: 11))
                .foregroundStyle(RideMeshTheme.muted)
                .lineSpacing(2)

            if RideMeshWiFiAware.supported {
                DevicePairingView(.wifiAware(.connecting(to: .rideMesh, from: .selected([])))) {
                    discoveryButton(title: "MAKE THIS IPHONE DISCOVERABLE", symbol: "dot.radiowaves.left.and.right")
                } fallback: {
                    discoveryButton(title: "PAIRING NOT AVAILABLE", symbol: "exclamationmark.triangle")
                }

                DevicePicker(.wifiAware(.connecting(to: .selected([]), from: .rideMesh))) { _ in
                    selectedPeer = true
                } label: {
                    discoveryButton(title: "FIND NEARBY RIDEMESH PEERS", symbol: "magnifyingglass")
                } fallback: {
                    discoveryButton(title: "BROWSING NOT AVAILABLE", symbol: "exclamationmark.triangle")
                }

                if selectedPeer {
                    Label("Peer selected. Wi-Fi Aware pairing succeeded.", systemImage: "checkmark.circle.fill")
                        .font(.system(size: 10.5, weight: .semibold))
                        .foregroundStyle(RideMeshTheme.green)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(18)
        .rmPanel(radius: 18, border: RideMeshTheme.borderStrong)
    }

    private func discoveryButton(title: String, symbol: String) -> some View {
        HStack(spacing: 9) {
            Image(systemName: symbol)
            Text(title)
        }
        .font(.system(size: 10, weight: .bold))
        .foregroundStyle(RideMeshTheme.darkTextOnAccent)
        .frame(maxWidth: .infinity, minHeight: 48)
        .background(RideMeshTheme.accent)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}
