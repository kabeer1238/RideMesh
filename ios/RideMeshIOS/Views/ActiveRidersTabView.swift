import SwiftUI

struct ActiveRidersTabView: View {
    @EnvironmentObject private var model: RideMeshViewModel

    var body: some View {
        VStack(spacing: 0) {
            RMActiveHeader(title: "RIDERS", subtitle: "\(model.groupRiderCount) IN THIS RIDE")

            ScrollView(showsIndicators: false) {
                VStack(spacing: 9) {
                    ActiveRiderRow(name: model.riderName, detail: "CONNECTED • YOU", quality: .excellent, live: true)
                    ForEach(model.peers) { peer in
                        ActiveRiderRow(
                            name: peer.displayName,
                            detail: peer.connected ? peer.connectionQuality.rawValue : "RECONNECTING…",
                            quality: peer.connectionQuality,
                            live: peer.connected
                        )
                    }

                    if model.peers.isEmpty {
                        VStack(spacing: 9) {
                            Image(systemName: "person.3")
                                .font(.system(size: 24, weight: .semibold))
                                .foregroundStyle(RideMeshTheme.faint)
                            Text("Other riders will appear here after they join the same Ride Code.")
                                .font(.system(size: 11))
                                .foregroundStyle(RideMeshTheme.muted)
                                .multilineTextAlignment(.center)
                        }
                        .padding(.top, 38)
                        .padding(.horizontal, 30)
                    }
                }
                .padding(.horizontal, 18)
                .padding(.top, 14)
                .padding(.bottom, 24)
            }
        }
        .background(RideMeshBackground())
    }
}

private struct ActiveRiderRow: View {
    let name: String
    let detail: String
    let quality: RiderConnectionQuality
    let live: Bool

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(live ? RideMeshTheme.accentDim : RideMeshTheme.panel2)
                .overlay(Image(systemName: "person.fill").foregroundStyle(live ? RideMeshTheme.accent : RideMeshTheme.muted))
                .frame(width: 44, height: 44)
            VStack(alignment: .leading, spacing: 4) {
                Text(name)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(RideMeshTheme.white)
                Text(detail)
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(live ? qualityColor : RideMeshTheme.muted)
            }
            Spacer()
            Text(String(repeating: "•", count: quality.bars))
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(qualityColor)
        }
        .padding(.horizontal, 14)
        .frame(minHeight: 68)
        .rmPanel(radius: 14)
    }

    private var qualityColor: Color {
        switch quality {
        case .excellent, .good: return RideMeshTheme.green
        case .poor: return RideMeshTheme.amber
        case .reconnecting: return RideMeshTheme.danger
        }
    }
}

struct RMActiveHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(RideMeshTheme.condensed(23, weight: .bold))
                    .tracking(1.0)
                    .foregroundStyle(RideMeshTheme.white)
                Text(subtitle)
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(RideMeshTheme.accent)
            }
            Spacer()
            Image("RideMeshIconExact")
                .resizable()
                .scaledToFit()
                .frame(width: 36, height: 36)
        }
        .padding(.horizontal, 18)
        .padding(.top, 14)
        .padding(.bottom, 10)
        .rmPanel(radius: 0, fill: RideMeshTheme.surface, border: RideMeshTheme.border, glassTint: RideMeshTheme.surface.opacity(0.30))
    }
}
