import SwiftUI

struct ActiveRideShellView: View {
    @EnvironmentObject private var model: RideMeshViewModel

    var body: some View {
        ZStack(alignment: .bottom) {
            Group {
                switch model.activeTab {
                case .ride:
                    ActiveRideView()
                case .map:
                    LiveRiderMapView()
                case .riders:
                    ActiveRidersTabView()
                case .settings:
                    ActiveSettingsTabView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(.bottom, 72)

            RideMainTabBar()
                .padding(.horizontal, 12)
                .padding(.bottom, 7)
        }
        .background(RideMeshBackground())
    }
}

private struct RideMainTabBar: View {
    @EnvironmentObject private var model: RideMeshViewModel

    var body: some View {
        HStack(spacing: 4) {
            ForEach(RideMainTab.allCases) { tab in
                Button {
                    withAnimation(.easeInOut(duration: 0.18)) {
                        model.selectActiveTab(tab)
                    }
                } label: {
                    VStack(spacing: 4) {
                        Image(systemName: tab.symbol)
                            .font(.system(size: 16, weight: .semibold))
                            .symbolRenderingMode(.monochrome)
                        Text(tab.rawValue)
                            .font(.system(size: 8, weight: .bold))
                    }
                    .foregroundStyle(model.activeTab == tab ? RideMeshTheme.accent : RideMeshTheme.whiteSoft)
                    .frame(maxWidth: .infinity, minHeight: 54)
                    .background(
                        model.activeTab == tab
                            ? RideMeshTheme.accent.opacity(0.10)
                            : Color.clear
                    )
                    .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(6)
        .rmPanel(
            radius: 24,
            fill: RideMeshTheme.surface,
            border: RideMeshTheme.borderStrong,
            glassTint: RideMeshTheme.panel.opacity(0.34),
            interactive: true
        )
    }
}
