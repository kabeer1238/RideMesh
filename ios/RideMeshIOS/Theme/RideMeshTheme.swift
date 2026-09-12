import SwiftUI
import UIKit

extension Color {
    init(hex: UInt32, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: alpha
        )
    }
}

enum RideMeshTheme {
    // RideMesh identity stays black + cyan, while the presentation adopts
    // iOS Liquid Glass on iOS 26 and a material fallback on older iOS versions.
    static let black = Color(hex: 0x020505)
    static let surface = Color(hex: 0x07100F)
    static let panel = Color(hex: 0x0C1514)
    static let panel2 = Color(hex: 0x111B1A)
    static let livePanel = Color(hex: 0x081716)
    static let white = Color(hex: 0xF5F8F7)
    static let muted = Color(hex: 0x95A3A0)
    static let faint = Color(hex: 0x53605D)
    static let faintPlus = Color(hex: 0x73817E)
    static let whiteSoft = Color(hex: 0xDCE4E2)
    static let accent = Color(hex: 0x00E5D4)
    static let accentDim = Color(hex: 0x00E5D4, alpha: 0.14)
    static let accentSoft = Color(hex: 0x65FFF2)
    static let green = Color(hex: 0x49E38F)
    static let amber = Color(hex: 0xFFC24B)
    static let danger = Color(hex: 0xFF5F70)
    static let endRed = Color(hex: 0xFF655E)
    static let border = Color.white.opacity(0.085)
    static let borderStrong = Color.white.opacity(0.15)
    static let darkTextOnAccent = Color(hex: 0x00201D)

    static let heroGradient = LinearGradient(
        colors: [Color(hex: 0x06110F), Color(hex: 0x0A2220), Color(hex: 0x020606)],
        startPoint: .bottomTrailing,
        endPoint: .topLeading
    )

    static let cyanGlowGradient = LinearGradient(
        colors: [accent.opacity(0.30), accent.opacity(0.04), .clear],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
    )

    static func condensed(_ size: CGFloat, weight: UIFont.Weight = .bold) -> Font {
        Font(UIFont.systemFont(ofSize: size, weight: weight, width: .condensed))
    }
}

/// App-wide dark atmospheric background. It deliberately keeps the content
/// surface restrained so Liquid Glass remains legible instead of becoming noisy.
struct RideMeshBackground: View {
    var body: some View {
        ZStack {
            RideMeshTheme.black

            RadialGradient(
                colors: [RideMeshTheme.accent.opacity(0.16), .clear],
                center: .topTrailing,
                startRadius: 8,
                endRadius: 360
            )

            RadialGradient(
                colors: [Color.white.opacity(0.055), .clear],
                center: .bottomLeading,
                startRadius: 0,
                endRadius: 300
            )
        }
        .ignoresSafeArea()
    }
}

struct RMPanel: ViewModifier {
    var radius: CGFloat = 18
    var fill: Color = RideMeshTheme.panel
    var border: Color = RideMeshTheme.border
    var lineWidth: CGFloat = 1
    var glassTint: Color? = nil
    var interactive = false

    @ViewBuilder
    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)

        if #available(iOS 26.0, *) {
            content
                .glassEffect(
                    .regular
                        .tint(glassTint ?? fill.opacity(0.34))
                        .interactive(interactive),
                    in: shape
                )
                .overlay(shape.stroke(border, lineWidth: lineWidth))
        } else {
            content
                .background(.ultraThinMaterial, in: shape)
                .background((glassTint ?? fill).opacity(0.72), in: shape)
                .overlay(shape.stroke(border, lineWidth: lineWidth))
        }
    }
}

struct RMCircleGlass: ViewModifier {
    var tint: Color? = nil
    var interactive = true

    @ViewBuilder
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            content
                .glassEffect(
                    .regular.tint(tint?.opacity(0.42)).interactive(interactive),
                    in: Circle()
                )
        } else {
            content
                .background(.ultraThinMaterial, in: Circle())
                .background((tint ?? RideMeshTheme.panel).opacity(0.58), in: Circle())
                .overlay(Circle().stroke(RideMeshTheme.borderStrong, lineWidth: 1))
        }
    }
}

struct RMGlassButtonModifier: ViewModifier {
    var prominent = false
    var tint: Color = RideMeshTheme.accent

    @ViewBuilder
    func body(content: Content) -> some View {
        if #available(iOS 26.0, *) {
            if prominent {
                content
                    .buttonStyle(.glassProminent)
                    .tint(tint)
            } else {
                content
                    .buttonStyle(.glass)
                    .tint(tint)
            }
        } else {
            content
                .buttonStyle(.plain)
        }
    }
}

extension View {
    func rmPanel(
        radius: CGFloat = 18,
        fill: Color = RideMeshTheme.panel,
        border: Color = RideMeshTheme.border,
        lineWidth: CGFloat = 1,
        glassTint: Color? = nil,
        interactive: Bool = false
    ) -> some View {
        modifier(RMPanel(
            radius: radius,
            fill: fill,
            border: border,
            lineWidth: lineWidth,
            glassTint: glassTint,
            interactive: interactive
        ))
    }

    func rmCircleGlass(tint: Color? = nil, interactive: Bool = true) -> some View {
        modifier(RMCircleGlass(tint: tint, interactive: interactive))
    }

    func rmGlassButton(prominent: Bool = false, tint: Color = RideMeshTheme.accent) -> some View {
        modifier(RMGlassButtonModifier(prominent: prominent, tint: tint))
    }
}
