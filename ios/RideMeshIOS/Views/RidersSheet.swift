import SwiftUI

struct RidersSheet: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            RideMeshBackground()
            VStack(spacing: 0) {
                RMModalHeader(title: "RIDERS") { dismiss() }

                ScrollView(showsIndicators: false) {
                    VStack(spacing: 8) {
                        RiderSheetRow(name: model.riderName, detail: "CONNECTED • YOU", live: true)
                        ForEach(model.peers) { peer in
                            RiderSheetRow(
                                name: peer.displayName,
                                detail: peer.connected ? peer.connectionQuality.rawValue : "RECONNECTING…",
                                live: peer.connected
                            )
                        }

                        if model.peers.isEmpty {
                            Text("Other riders will appear here quickly after they join the same Ride Code.")
                                .font(.system(size: 11))
                                .foregroundStyle(RideMeshTheme.muted)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal, 24)
                                .padding(.top, 24)
                        }
                    }
                    .padding(.top, 14)
                }
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
        }
        .preferredColorScheme(.dark)
    }
}

private struct RiderSheetRow: View {
    let name: String
    let detail: String
    let live: Bool

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(live ? RideMeshTheme.accentDim : RideMeshTheme.panel2)
                .overlay(Image(systemName: "person.fill").foregroundStyle(live ? RideMeshTheme.accent : RideMeshTheme.muted))
                .frame(width: 42, height: 42)
            VStack(alignment: .leading, spacing: 4) {
                Text(name).font(.system(size: 13, weight: .bold)).foregroundStyle(RideMeshTheme.white)
                Text(detail).font(.system(size: 9, weight: .bold)).foregroundStyle(live ? RideMeshTheme.green : RideMeshTheme.muted)
            }
            Spacer()
        }
        .padding(.horizontal, 14)
        .frame(minHeight: 66)
        .rmPanel(radius: 14)
    }
}
