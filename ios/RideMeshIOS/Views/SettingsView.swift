import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var editedName = ""
    @FocusState private var nameFocused: Bool

    var body: some View {
        ZStack {
            RideMeshBackground()

            ScrollView(showsIndicators: false) {
                VStack(spacing: 0) {
                    RMModalHeader(title: "SETTINGS") { dismiss() }

                    Toggle("HYBRID VOICE • 8 RIDERS",isOn:$model.hybridEnabled)
                        .disabled(model.isRideActive)
                        .onChange(of:model.hybridEnabled) { _ in model.persist() }
                        .padding()
                    Text("Connect through internet and nearby riders. End the ride before changing mode.")
                        .font(.caption).foregroundStyle(RideMeshTheme.muted)
                    profilePanel
                        .padding(.top, 14)

                    sectionLabel("RIDE")
                        .padding(.top, 22)

                    VStack(spacing: 0) {
                        RMSettingRow(title: "AUDIO ROUTE", detail: model.audioRoute.dialogTitle, symbol: "headphones")
                            .contentShape(Rectangle())
                            .onTapGesture { dismiss(); model.showAudioRoutes = true }

                        Rectangle().fill(RideMeshTheme.border).frame(height: 1)

                        RMSettingRow(title: "OFFLINE DISCOVERY", detail: "Direct nearby RideMesh pairing test", symbol: "antenna.radiowaves.left.and.right")
                            .contentShape(Rectangle())
                            .onTapGesture { dismiss(); model.showOfflineDiscovery = true }

                        Rectangle().fill(RideMeshTheme.border).frame(height: 1)

                        Link(destination: URL(string: "https://chat.whatsapp.com/CGToJCBDG6XFGUpeTp7uKW")!) {
                            RMSettingRow(title: "RIDEMESH COMMUNITY", detail: "Support, feedback and rider discussion", symbol: "message.fill")
                        }
                    }
                    .rmPanel(radius: 18)
                    .padding(.top, 8)

                    sectionLabel("BATTERY")
                        .padding(.top, 22)

                    Toggle(isOn: $model.batterySaver) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("BATTERY SMART")
                                .font(.system(size: 11, weight: .bold))
                                .foregroundStyle(RideMeshTheme.white)
                            Text("Reduces nonessential background work before voice quality is affected.")
                                .font(.system(size: 10))
                                .foregroundStyle(RideMeshTheme.muted)
                        }
                    }
                    .tint(RideMeshTheme.accent)
                    .onChange(of: model.batterySaver) { _ in model.persist() }
                    .padding(16)
                    .rmPanel(radius: 18)
                    .padding(.top, 8)

                    sectionLabel("LEGAL")
                        .padding(.top, 22)

                    VStack(spacing: 0) {
                        Link(destination: URL(string: "https://autopilotindia.com/ridemesh-privacy-policy/")!) {
                            RMSettingRow(title: "PRIVACY POLICY", detail: "How RideMesh handles your data", symbol: "hand.raised.fill")
                        }
                        Rectangle().fill(RideMeshTheme.border).frame(height: 1)
                        Link(destination: URL(string: "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/")!) {
                            RMSettingRow(title: "TERMS OF USE", detail: "Apple Standard EULA", symbol: "doc.text.fill")
                        }
                    }
                    .rmPanel(radius: 18)
                    .padding(.top, 8)

                    Text("RIDEMESH BY AUTOPILOT INDIA • VERSION 1.0")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundStyle(RideMeshTheme.faintPlus)
                        .padding(.top, 24)
                        .padding(.bottom, 28)
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)
            }
        }
        .preferredColorScheme(.dark)
        .scrollDismissesKeyboard(.interactively)
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { nameFocused = false }
            }
        }
        .onAppear { editedName = model.riderName }
    }

    private var profilePanel: some View {
        VStack(alignment: .leading, spacing: 0) {
            sectionLabel("RIDER PROFILE")

            Text("This is the name other riders see. No RideMesh account or password is required.")
                .font(.system(size: 11))
                .foregroundStyle(RideMeshTheme.muted)
                .lineSpacing(2)
                .padding(.top, 8)

            TextField("Rider name", text: $editedName)
                .keyboardType(.default)
                .textContentType(.name)
                .textInputAutocapitalization(.words)
                .autocorrectionDisabled(true)
                .submitLabel(.done)
                .foregroundStyle(RideMeshTheme.white)
                .font(.system(size: 16, weight: .semibold))
                .focused($nameFocused)
                .frame(height: 50)
                .onSubmit { nameFocused = false }
                .onChange(of: editedName) { value in
                    if value.count > 18 { editedName = String(value.prefix(18)) }
                }

            Rectangle().fill(RideMeshTheme.accent.opacity(0.7)).frame(height: 1)

            HStack(spacing: 10) {
                Button {
                    nameFocused = false
                    let clean = editedName.trimmingCharacters(in: .whitespacesAndNewlines)
                    model.riderName = clean.isEmpty ? "Rider" : clean
                    model.persist()
                } label: {
                    Text("SAVE NAME")
                        .font(.system(size: 10.5, weight: .bold))
                        .foregroundStyle(RideMeshTheme.darkTextOnAccent)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .background(RideMeshTheme.accent)
                        .clipShape(RoundedRectangle(cornerRadius: 15, style: .continuous))
                }
                .buttonStyle(.plain)

                Button {
                    dismiss()
                    DispatchQueue.main.async { model.editRiderProfile() }
                } label: {
                    Text("RIDER SETUP")
                        .font(.system(size: 10.5, weight: .bold))
                        .foregroundStyle(RideMeshTheme.white)
                        .frame(maxWidth: .infinity, minHeight: 48)
                        .rmPanel(radius: 15, interactive: true)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 14)
        }
        .padding(18)
        .rmPanel(radius: 20)
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .bold))
            .foregroundStyle(RideMeshTheme.faintPlus)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct RMModalHeader: View {
    let title: String
    let close: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            Color.clear.frame(width: 52, height: 44)
            Text(title)
                .font(RideMeshTheme.condensed(18, weight: .bold))
                .tracking(1.2)
                .foregroundStyle(RideMeshTheme.white)
                .frame(maxWidth: .infinity)
            Button { close() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(RideMeshTheme.white)
                    .frame(width: 38, height: 38)
                    .rmCircleGlass()
            }
            .buttonStyle(.plain)
            .frame(width: 52, height: 44)
        }
        .frame(height: 52)
    }
}

struct RMSettingRow: View {
    let title: String
    let detail: String
    let symbol: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(RideMeshTheme.accent)
                .frame(width: 30)
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
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(RideMeshTheme.faintPlus)
        }
        .padding(.horizontal, 14)
        .frame(minHeight: 62)
    }
}
