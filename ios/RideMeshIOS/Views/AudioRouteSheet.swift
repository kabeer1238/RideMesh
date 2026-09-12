import SwiftUI

struct AudioRouteSheet: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            RideMeshBackground()
            VStack(spacing: 0) {
                RMModalHeader(title: "AUDIO ROUTE") { dismiss() }

                Text("Choose where RideMesh voice should play. Automatic is recommended while riding.")
                    .font(.system(size: 12))
                    .foregroundStyle(RideMeshTheme.muted)
                    .lineSpacing(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.top, 14)

                VStack(spacing: 0) {
                    ForEach(RideAudioRoute.allCases) { route in
                        Button {
                            model.chooseAudioRoute(route)
                        } label: {
                            HStack(spacing: 12) {
                                Image(systemName: model.audioRoute == route ? "largecircle.fill.circle" : "circle")
                                    .foregroundStyle(model.audioRoute == route ? RideMeshTheme.accent : RideMeshTheme.muted)
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(route.dialogTitle)
                                        .font(.system(size: 12, weight: .bold))
                                        .foregroundStyle(RideMeshTheme.white)
                                    Text(route.title)
                                        .font(.system(size: 10))
                                        .foregroundStyle(RideMeshTheme.muted)
                                }
                                Spacer()
                            }
                            .padding(.horizontal, 14)
                            .frame(minHeight: 64)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .rmPanel(radius: 16)
                .padding(.top, 16)

                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
        }
        .preferredColorScheme(.dark)
    }
}
