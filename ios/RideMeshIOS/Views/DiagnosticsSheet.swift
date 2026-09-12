import SwiftUI

// Public rider-facing status only. Protocol, codec, signaling, peer negotiation,
// packet counters and infrastructure diagnostics intentionally stay out of this UI.
struct DiagnosticsSheet: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            RideMeshBackground()
            ScrollView(showsIndicators: false) {
                VStack(spacing: 0) {
                    RMModalHeader(title: "RIDE STATUS") { dismiss() }

                    if model.hybridEnabled {
                        Text(model.hybrid.summary).font(.caption).foregroundStyle(RideMeshTheme.accent).padding()
                    }
                    statusHero
                        .padding(.top, 14)

                    VStack(spacing: 0) {
                        StatusRow(label: "Connection", value: connectionText, accent: connectionText == "Good")
                        StatusDivider()
                        StatusRow(label: "Voice", value: voiceText)
                        StatusDivider()
                        StatusRow(label: "Headset", value: headsetText)
                        StatusDivider()
                        StatusRow(label: "Riders", value: "\(model.totalConnectedRiders) connected")
                        StatusDivider()
                        StatusRow(label: "Audio Quality", value: audioQualityText)
                        StatusDivider()
                        StatusRow(label: "Music", value: model.voice.smartDuckingActive ? "Lowered for speech" : "Normal")
                        StatusDivider()
                        StatusRow(label: "Battery Smart", value: model.batterySaver ? "On" : "Off")
                    }
                    .rmPanel(radius: 16)
                    .padding(.top, 14)

                    Text("RideMesh automatically handles temporary connection changes and call interruptions. Technical diagnostics are not shown in the normal rider interface.")
                        .font(.system(size: 10.5))
                        .foregroundStyle(RideMeshTheme.muted)
                        .lineSpacing(2)
                        .padding(14)
                        .rmPanel(radius: 12)
                        .padding(.top, 12)
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)
                .padding(.bottom, 24)
            }
        }
        .preferredColorScheme(.dark)
    }

    private var connectionText: String {
        if !model.network.isOnline { return "Waiting for internet" }
        if model.peers.contains(where: { $0.connectionQuality == .reconnecting }) { return "Reconnecting…" }
        if model.peers.contains(where: { $0.connectionQuality == .poor }) { return "Poor" }
        return model.voice.diagnostics.signalingConnected ? "Good" : "Reconnecting…"
    }

    private var voiceText: String {
        if model.micMuted { return "Muted" }
        if model.connectedVoicePeers > 0 { return "Ready" }
        return model.voice.diagnostics.signalingConnected ? "Ready" : "Connecting…"
    }

    private var headsetText: String {
        model.audio.helmetAvailable ? "Connected" : (model.audioRoute == .phone ? "Phone audio" : "Ready")
    }

    private var audioQualityText: String {
        if !model.network.isOnline { return "Waiting" }
        if model.peers.contains(where: { $0.connectionQuality == .poor }) { return "Poor" }
        if !model.peers.isEmpty && model.peers.allSatisfy({ $0.connectionQuality == .excellent }) { return "Excellent" }
        if model.peers.contains(where: { $0.connectionQuality == .reconnecting }) { return "Recovering" }
        return model.voice.diagnostics.signalingConnected ? "Good" : "Recovering"
    }

    private var statusHero: some View {
        HStack(spacing: 12) {
            RideMeshIconView(size: 46)
            VStack(alignment: .leading, spacing: 4) {
                Text(model.connectionLabel)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(RideMeshTheme.accent)
                Text("Ride \(model.normalizedRideCode)")
                    .font(.system(size: 10))
                    .foregroundStyle(RideMeshTheme.muted)
            }
            Spacer()
        }
        .padding(16)
        .rmPanel(radius: 16, border: RideMeshTheme.borderStrong)
    }
}

private struct StatusRow: View {
    let label: String
    let value: String
    var accent = false

    var body: some View {
        HStack(spacing: 12) {
            Text(label)
                .font(.system(size: 10.5, weight: .semibold))
                .foregroundStyle(RideMeshTheme.white)
            Spacer()
            Text(value)
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(accent ? RideMeshTheme.accent : RideMeshTheme.muted)
                .multilineTextAlignment(.trailing)
        }
        .padding(.horizontal, 14)
        .frame(minHeight: 54)
    }
}

private struct StatusDivider: View {
    var body: some View { Rectangle().fill(RideMeshTheme.border).frame(height: 1) }
}
