import SwiftUI

struct RootView: View {
    @EnvironmentObject private var model: RideMeshViewModel

    var body: some View {
        ZStack {
            RideMeshBackground()

            switch model.screen {
            case .profile:
                RiderProfileView()
            case .home:
                HomeView()
            case .setup:
                RideSetupView()
            case .active:
                ActiveRideShellView()
            }
        }
        .tint(RideMeshTheme.accent)
        .sheet(isPresented: $model.showSettings) {
            SettingsView().presentationDetents([.large]).presentationDragIndicator(.hidden)
        }
        .sheet(isPresented: $model.showQR) {
            QRCodeSheet().presentationDetents([.large]).presentationDragIndicator(.hidden)
        }
        .fullScreenCover(isPresented: $model.showScanner) {
            QRScannerView { model.acceptScannedCode($0) }
        }
        .sheet(isPresented: $model.showRiders) {
            RidersSheet().presentationDetents([.medium, .large]).presentationDragIndicator(.hidden)
        }
        .sheet(isPresented: $model.showInvite) {
            InviteSheet().presentationDetents([.medium]).presentationDragIndicator(.hidden)
        }
        .sheet(isPresented: $model.showAudioRoutes) {
            AudioRouteSheet().presentationDetents([.medium]).presentationDragIndicator(.hidden)
        }
        .sheet(isPresented: $model.showDiagnostics) {
            DiagnosticsSheet().presentationDetents([.medium, .large]).presentationDragIndicator(.hidden)
        }
        .sheet(isPresented: $model.showOfflineDiscovery) {
            OfflineDiscoveryView().presentationDetents([.medium, .large]).presentationDragIndicator(.hidden)
        }
        .alert("End ride?", isPresented: $model.confirmEndRide) {
            Button("CANCEL", role: .cancel) { model.confirmEndRide = false }
            Button("END RIDE", role: .destructive) { model.stopRide() }
        } message: {
            Text("RideMesh will disconnect this ride and release the microphone and active communication resources.")
        }
        .alert("RideMesh", isPresented: Binding(
            get: { model.errorMessage != nil },
            set: { if !$0 { model.dismissError() } }
        )) {
            Button("OK", role: .cancel) { model.dismissError() }
        } message: {
            Text(model.errorMessage ?? "")
        }
    }
}
