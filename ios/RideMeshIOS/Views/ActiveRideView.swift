import SwiftUI

struct ActiveRideView: View {
    @EnvironmentObject private var model: RideMeshViewModel

    var body: some View {
        VStack(spacing: 0) {
            Image("RideMeshLogoExact")
                .resizable()
                .scaledToFit()
                .mask(alignment: .top) { Rectangle().scaleEffect(x: 1, y: 0.88, anchor: .top) }
                .blendMode(.screen)
                .frame(width: 244, height: 72, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)

            Text("RIDE ACTIVE")
                .font(RideMeshTheme.condensed(28, weight: .bold))
                .foregroundStyle(RideMeshTheme.white)
                .frame(maxWidth: .infinity)
                .padding(.top, 10)

            Text(activeMeshStatus)
                .font(.system(size: 12, weight: .bold))
                .foregroundStyle(RideMeshTheme.accent)
                .frame(maxWidth: .infinity)
                .padding(.top, 5)

            HStack(spacing: 8) {
                ActiveStatusTile(
                    text: model.network.isOnline ? (model.voice.diagnostics.signalingConnected ? "CONNECTED" : "RECONNECTING") : "OFFLINE",
                    color: RideMeshTheme.accent
                )
                ActiveStatusTile(
                    text: model.micMuted ? "MIC MUTED" : "VOICE CLEAN",
                    color: RideMeshTheme.white
                )
                ActiveStatusTile(
                    text: model.batterySaver ? "SMART POWER" : "POWER NORMAL",
                    color: RideMeshTheme.green
                )
            }
            .frame(height: 46)
            .padding(.top, 11)

            livePanel
                .padding(.top, 12)

            riderGrid
                .padding(.top, 10)
                .frame(maxHeight: .infinity)

            HStack(spacing: 8) {
                ActiveBottomButton(title: "INVITE", color: RideMeshTheme.accent, stroke: RideMeshTheme.accent) {
                    model.showInvite = true
                }
                ActiveBottomButton(title: "AUDIO", color: RideMeshTheme.white, stroke: RideMeshTheme.border) {
                    model.showAudioRoutes = true
                }
                ActiveBottomButton(title: "STATUS", color: RideMeshTheme.white, stroke: RideMeshTheme.border) {
                    model.showDiagnostics = true
                }
            }
            .frame(height: 54)
            .padding(.bottom, 2)
        }
        .padding(.horizontal, 18)
        .padding(.top, 14)
        .padding(.bottom, 14)
        .background(RideMeshBackground())
    }

    private var activeMeshStatus: String {
        if !model.network.isOnline { return "WAITING FOR INTERNET" }
        if model.connectedVoicePeers > 0 { return "\(model.connectedVoicePeers + 1) RIDERS CONNECTED" }
        return model.voice.diagnostics.signalingConnected ? "READY • WAITING FOR RIDERS" : "RECONNECTING…"
    }

    private var livePanel: some View {
        VStack(spacing: 14) {
            HStack(spacing: 12) {
                Image(systemName: "waveform")
                    .font(.system(size: 27, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.accent)
                VStack(alignment: .leading, spacing: 3) {
                    Text(model.micMuted ? "MUTED" : "LIVE")
                        .font(RideMeshTheme.condensed(25, weight: .bold))
                        .foregroundStyle(model.micMuted ? RideMeshTheme.amber : RideMeshTheme.accent)
                    Text("HANDS-FREE INTERCOM")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(RideMeshTheme.white)
                    Text(model.micMuted ? "LISTENING ONLY" : "ONLINE INTERCOM")
                        .font(.system(size: 9))
                        .foregroundStyle(RideMeshTheme.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Rectangle()
                    .fill(RideMeshTheme.borderStrong)
                    .frame(width: 1, height: 48)
                VStack(alignment: .leading, spacing: 5) {
                    Text("RIDE CODE")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(RideMeshTheme.muted)
                    Text(model.normalizedRideCode)
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(RideMeshTheme.white)
                        .lineLimit(1)
                        .minimumScaleFactor(0.7)
                }
            }
            HStack(spacing: 12) {
                Button { model.toggleMute() } label: {
                    Label(model.micMuted ? "UNMUTE" : "MUTE MIC",
                          systemImage: model.micMuted ? "mic.slash.fill" : "mic.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(RideMeshTheme.white)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(RideMeshTheme.panel2, in: RoundedRectangle(cornerRadius: 16))
                        .overlay(RoundedRectangle(cornerRadius: 16).stroke(RideMeshTheme.accent, lineWidth: 1.5))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(model.micMuted ? "Unmute microphone" : "Mute microphone")
                Button { model.requestEndRide() } label: {
                    Label("END", systemImage: "phone.down.fill")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity, minHeight: 52)
                        .background(Color(red: 0.67, green: 0.10, blue: 0.16), in: RoundedRectangle(cornerRadius: 16))
                        .overlay(RoundedRectangle(cornerRadius: 16).stroke(RideMeshTheme.endRed, lineWidth: 1.5))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("End ride")
            }
        }
        .padding(16)
        .rmPanel(radius: 20, fill: RideMeshTheme.livePanel, border: RideMeshTheme.accent.opacity(0.70), glassTint: RideMeshTheme.accent.opacity(0.08))
    }

    private var riderGrid: some View {
        let riders = [localRider] + model.peers.map { peer in
            RiderTileData(
                name: peer.displayName,
                detail: peer.connected ? peer.connectionQuality.rawValue : RiderConnectionQuality.reconnecting.rawValue,
                live: peer.connected,
                quality: peer.connectionQuality
            )
        }
        return LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
            ForEach(Array(riders.prefix(6).enumerated()), id: \.offset) { _, rider in
                RiderTile(data: rider)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private var localRider: RiderTileData {
        RiderTileData(name: model.riderName, detail: model.micMuted ? "MUTED • YOU" : "LIVE • YOU", live: !model.micMuted, quality: .excellent)
    }
}

private struct RiderTileData {
    let name: String
    let detail: String
    let live: Bool
    let quality: RiderConnectionQuality
}

private struct RiderTile: View {
    let data: RiderTileData

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(data.live ? RideMeshTheme.accentDim : RideMeshTheme.panel2)
                .overlay(
                    Image(systemName: "person.fill")
                        .font(.system(size: 15, weight: .bold))
                        .foregroundStyle(data.live ? RideMeshTheme.accent : RideMeshTheme.muted)
                )
                .frame(width: 38, height: 38)

            VStack(alignment: .leading, spacing: 3) {
                Text(data.name)
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(RideMeshTheme.white)
                    .lineLimit(1)
                HStack(spacing: 5) {
                    Text(data.detail)
                        .font(.system(size: 8.5, weight: .bold))
                        .foregroundStyle(data.live ? RideMeshTheme.green : RideMeshTheme.muted)
                        .lineLimit(1)
                    if data.live {
                        Text(String(repeating: "•", count: data.quality.bars))
                            .font(.system(size: 7, weight: .bold))
                            .foregroundStyle(data.quality == .poor ? RideMeshTheme.amber : RideMeshTheme.accent)
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 11)
        .frame(maxWidth: .infinity, minHeight: 62)
        .rmPanel(radius: 15, interactive: true)
    }
}

private struct ActiveStatusTile: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.system(size: 10, weight: .bold))
            .foregroundStyle(color)
            .lineLimit(1)
            .minimumScaleFactor(0.65)
            .frame(maxWidth: .infinity, minHeight: 38, maxHeight: 38)
            .rmPanel(radius: 16, interactive: false)
    }
}

private struct ActiveBottomButton: View {
    let title: String
    let color: Color
    let stroke: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(color)
                .frame(maxWidth: .infinity, minHeight: 54, maxHeight: 54)
                .rmPanel(radius: 15, border: stroke.opacity(0.75), glassTint: color.opacity(0.06), interactive: true)
        }
        .buttonStyle(.plain)
    }
}
