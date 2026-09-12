import SwiftUI

@main
struct RideMeshApp: App {
    @StateObject private var model = RideMeshViewModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
                .preferredColorScheme(.dark)
                .onOpenURL { model.handleOpenURL($0) }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active {
                model.handleAppBecameActive()
            }
        }
    }
}
