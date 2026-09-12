import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var model: RideMeshViewModel

    var body: some View {
        GeometryReader { geometry in
            let compactHeight = geometry.size.height < 760
            let horizontal = geometry.size.width >= 430 ? CGFloat(24) : CGFloat(18)
            let contentWidth = min(geometry.size.width - (horizontal * 2), CGFloat(540))

            ScrollView(showsIndicators: false) {
                VStack(spacing: compactHeight ? 13 : 16) {
                    header
                    hero(compact: compactHeight)
                    rideActions(compact: compactHeight)
                    readyCard(compact: compactHeight)

                    Text("Configure while stopped • Once the ride starts, normal voice mode is hands-free.")
                        .font(.system(size: 10))
                        .foregroundStyle(RideMeshTheme.faintPlus)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 22)
                        .padding(.top, 2)
                        .padding(.bottom, 18)
                }
                .frame(width: contentWidth)
                .frame(maxWidth: .infinity)
                .padding(.top, 8)
                .frame(minHeight: geometry.size.height, alignment: .top)
            }
        }
        .background(RideMeshBackground())
    }

    private var header: some View {
        HStack(spacing: 12) {
            RideMeshBrandView(width: 194, height: 58)
                .frame(maxWidth: .infinity, alignment: .leading)

            Button { model.showSettings = true } label: {
                Image(systemName: "gearshape.fill")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.white)
                    .frame(width: 42, height: 42)
                    .rmCircleGlass(interactive: true)
            }
            .buttonStyle(.plain)
        }
    }

    private func hero(compact: Bool) -> some View {
        VStack(alignment: .leading, spacing: compact ? 11 : 14) {
            HStack {
                Label("HANDS-FREE RIDER INTERCOM", systemImage: "waveform")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(RideMeshTheme.accent)
                Spacer()
                HStack(spacing: 5) {
                    Circle()
                        .fill(model.network.isOnline ? RideMeshTheme.green : RideMeshTheme.amber)
                        .frame(width: 7, height: 7)
                    Text(model.network.isOnline ? "READY" : "OFFLINE")
                        .font(.system(size: 8, weight: .bold))
                        .foregroundStyle(RideMeshTheme.whiteSoft)
                }
            }

            Text("YOUR GROUP.\nONE CHANNEL.")
                .font(RideMeshTheme.condensed(compact ? 31 : 35, weight: .bold))
                .tracking(0.7)
                .foregroundStyle(RideMeshTheme.white)

            Text("Clear group voice, live rider awareness and fast rider-to-rider actions — designed for the road.")
                .font(.system(size: compact ? 12.5 : 13.5))
                .foregroundStyle(RideMeshTheme.muted)
                .lineSpacing(3)

            HStack(spacing: 8) {
                heroChip("VOICE", "waveform")
                heroChip("LIVE MAP", "map.fill")
                heroChip("QR JOIN", "qrcode")
            }
        }
        .padding(compact ? 18 : 21)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RideMeshTheme.cyanGlowGradient.opacity(0.45))
        .rmPanel(radius: 26, fill: RideMeshTheme.livePanel, border: RideMeshTheme.borderStrong, glassTint: RideMeshTheme.accent.opacity(0.08))
    }

    private func heroChip(_ title: String, _ symbol: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: symbol)
            Text(title)
        }
        .font(.system(size: 8, weight: .bold))
        .foregroundStyle(RideMeshTheme.whiteSoft)
        .padding(.horizontal, 10)
        .frame(height: 29)
        .rmPanel(radius: 14, fill: RideMeshTheme.surface, border: RideMeshTheme.border, glassTint: RideMeshTheme.panel.opacity(0.35))
    }

    private func rideActions(compact: Bool) -> some View {
        HStack(spacing: 11) {
            RMOutlinedAction(
                title: "CREATE RIDE",
                symbol: "plus",
                iconColor: RideMeshTheme.darkTextOnAccent,
                textColor: RideMeshTheme.darkTextOnAccent,
                strokeColor: RideMeshTheme.accent,
                radius: 17,
                height: compact ? 54 : 58,
                fontSize: 11,
                prominent: true
            ) { model.createRide() }

            RMOutlinedAction(
                title: "JOIN RIDE",
                symbol: "arrow.right",
                iconColor: RideMeshTheme.white,
                textColor: RideMeshTheme.white,
                strokeColor: RideMeshTheme.borderStrong,
                radius: 17,
                height: compact ? 54 : 58,
                fontSize: 11
            ) { model.joinRide() }
        }
    }

    private func readyCard(compact: Bool) -> some View {
        VStack(alignment: .leading, spacing: 13) {
            HStack {
                Text("RIDE READINESS")
                    .font(RideMeshTheme.condensed(16, weight: .bold))
                    .tracking(0.7)
                    .foregroundStyle(RideMeshTheme.white)
                Spacer()
                Text("LIVE CHECK")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundStyle(RideMeshTheme.accent)
            }

            HStack(spacing: 0) {
                RMStatusColumn(
                    symbol: "antenna.radiowaves.left.and.right",
                    symbolSize: compact ? 22 : 24,
                    title: "CONNECTION",
                    titleSize: 9.5,
                    detail: model.network.isOnline ? "Voice Ready" : "Waiting for Internet"
                )

                statusDivider

                RMStatusColumn(
                    symbol: "headphones",
                    symbolSize: compact ? 22 : 24,
                    title: "HELMET",
                    titleSize: 9.5,
                    detail: model.audio.helmetAvailable ? "Connected" : "Phone Ready"
                )

                statusDivider

                RMStatusColumn(
                    symbol: "bolt.fill",
                    symbolSize: compact ? 22 : 24,
                    title: "POWER",
                    titleSize: 9.5,
                    detail: model.batterySaver ? "Smart Mode" : "Normal Mode"
                )
            }
        }
        .padding(16)
        .rmPanel(radius: 20)
    }

    private var statusDivider: some View {
        Rectangle()
            .fill(RideMeshTheme.borderStrong)
            .frame(width: 1, height: 58)
    }
}

struct RMOutlinedAction: View {
    let title: String
    let symbol: String?
    var iconColor: Color = RideMeshTheme.accent
    var textColor: Color = RideMeshTheme.white
    var strokeColor: Color = RideMeshTheme.border
    var radius: CGFloat = 14
    var height: CGFloat = 54
    var fontSize: CGFloat = 10
    var prominent: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                if let symbol {
                    Image(systemName: symbol)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(iconColor)
                }
                Text(title)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
            }
            .font(.system(size: fontSize, weight: .bold))
            .foregroundStyle(textColor)
            .frame(maxWidth: .infinity, minHeight: height, maxHeight: height)
            .background(prominent ? RideMeshTheme.accent : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: radius, style: .continuous)
                    .stroke(strokeColor, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .contentShape(Rectangle())
    }
}

private struct RMStatusColumn: View {
    let symbol: String
    let symbolSize: CGFloat
    let title: String
    let titleSize: CGFloat
    let detail: String

    var body: some View {
        VStack(spacing: 5) {
            Image(systemName: symbol)
                .font(.system(size: symbolSize, weight: .medium))
                .foregroundStyle(RideMeshTheme.accent)
                .frame(height: 28)

            Text(title)
                .font(.system(size: titleSize, weight: .bold))
                .foregroundStyle(RideMeshTheme.whiteSoft)
                .lineLimit(1)
                .minimumScaleFactor(0.72)

            Text(detail)
                .font(.system(size: 8.7))
                .foregroundStyle(RideMeshTheme.muted)
                .multilineTextAlignment(.center)
                .lineLimit(2)
                .minimumScaleFactor(0.72)
        }
        .frame(maxWidth: .infinity)
    }
}
