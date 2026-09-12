import SwiftUI

struct ActiveSettingsTabView: View {
    @EnvironmentObject private var model: RideMeshViewModel

    var body: some View {
        VStack(spacing: 0) {
            RMActiveHeader(title: "SETTINGS", subtitle: model.normalizedRideCode)

            ScrollView(showsIndicators: false) {
                VStack(spacing: 12) {
                    HStack(spacing: 12) {
                        Image(systemName: "person.fill")
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(RideMeshTheme.accent)
                            .frame(width: 28)
                        VStack(alignment: .leading, spacing: 3) {
                            Text("RIDER")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundStyle(RideMeshTheme.white)
                            Text(model.riderName + " • name changes available after END RIDE")
                                .font(.system(size: 10))
                                .foregroundStyle(RideMeshTheme.muted)
                                .lineLimit(1)
                                .minimumScaleFactor(0.75)
                        }
                        Spacer()
                    }
                    .padding(.horizontal, 14)
                    .frame(minHeight: 64)
                    .rmPanel(radius: 15)
                    settingRow(title: "AUDIO ROUTE", detail: model.audioRoute.dialogTitle, symbol: "headphones") {
                        model.showAudioRoutes = true
                    }

                    Toggle(isOn: $model.batterySaver) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("BATTERY SMART")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundStyle(RideMeshTheme.white)
                            Text("Reduces map/location and other nonessential work before voice quality is affected.")
                                .font(.system(size: 10))
                                .foregroundStyle(RideMeshTheme.muted)
                        }
                    }
                    .tint(RideMeshTheme.accent)
                    .onChange(of: model.batterySaver) { _ in model.persist() }
                    .padding(16)
                    .rmPanel(radius: 15)

                    VStack(alignment: .leading, spacing: 7) {
                        HStack {
                            Text("LIVE LOCATION")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundStyle(RideMeshTheme.white)
                            Spacer()
                            Text(model.isLocationSharing ? "SHARING" : "OFF")
                                .font(.system(size: 9, weight: .bold))
                                .foregroundStyle(model.isLocationSharing ? RideMeshTheme.accent : RideMeshTheme.muted)
                        }
                        Text("Location is shared only with riders in the current active RideMesh room and stops automatically at END RIDE.")
                            .font(.system(size: 10))
                            .foregroundStyle(RideMeshTheme.muted)
                            .lineSpacing(2)
                    }
                    .padding(16)
                    .rmPanel(radius: 15)

                    Link(destination: URL(string: "https://chat.whatsapp.com/CGToJCBDG6XFGUpeTp7uKW")!) {
                        HStack(spacing: 12) {
                            Image(systemName: "message.fill")
                                .foregroundStyle(RideMeshTheme.accent)
                                .frame(width: 28)
                            VStack(alignment: .leading, spacing: 3) {
                                Text("RIDEMESH COMMUNITY")
                                    .font(.system(size: 11, weight: .bold))
                                    .foregroundStyle(RideMeshTheme.white)
                                Text("Support, feedback and rider discussion")
                                    .font(.system(size: 10))
                                    .foregroundStyle(RideMeshTheme.muted)
                            }
                            Spacer()
                            Image(systemName: "arrow.up.right")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(RideMeshTheme.faint)
                        }
                        .padding(.horizontal, 14)
                        .frame(minHeight: 64)
                        .rmPanel(radius: 15)
                    }
                    .buttonStyle(.plain)

                    Button(role: .destructive) { model.requestEndRide() } label: {
                        Text("END RIDE")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(RideMeshTheme.endRed)
                            .frame(maxWidth: .infinity, minHeight: 52)
                            .overlay(RoundedRectangle(cornerRadius: 14).stroke(RideMeshTheme.endRed.opacity(0.7), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 8)
                }
                .padding(.horizontal, 18)
                .padding(.top, 14)
                .padding(.bottom, 28)
            }
        }
        .background(RideMeshBackground())
    }

    private func settingRow(title: String, detail: String, symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: symbol)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.accent)
                    .frame(width: 28)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(RideMeshTheme.white)
                    Text(detail)
                        .font(.system(size: 10))
                        .foregroundStyle(RideMeshTheme.muted)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(RideMeshTheme.faint)
            }
            .padding(.horizontal, 14)
            .frame(minHeight: 64)
            .rmPanel(radius: 15)
        }
        .buttonStyle(.plain)
    }
}
