import SwiftUI

struct RideSetupView: View {
    @EnvironmentObject private var model: RideMeshViewModel

    private enum Field: Hashable {
        case name
        case rideCode
        case phone
    }

    @FocusState private var focusedField: Field?

    var body: some View {
        GeometryReader { geometry in
            let compactHeight = geometry.size.height < 760
            let horizontal = geometry.size.width >= 430 ? CGFloat(24) : CGFloat(18)
            let contentWidth = min(geometry.size.width - (horizontal * 2), CGFloat(520))

            ScrollView(showsIndicators: false) {
                VStack(spacing: 0) {
                    setupHeader

                    Text(model.setupMode.helperText)
                        .font(.system(size: 11.5))
                        .foregroundStyle(RideMeshTheme.muted)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.top, compactHeight ? 4 : 7)

                    riderPanel
                        .padding(.top, compactHeight ? 10 : 14)

                    Text("AUDIO ROUTE")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(RideMeshTheme.faint)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, compactHeight ? 15 : 20)

                    audioRoutePanel(compact: compactHeight)
                        .padding(.top, 7)

                    batteryPanel
                        .padding(.top, compactHeight ? 10 : 13)

                    Button {
                        focusedField = nil
                        model.startRide()
                    } label: {
                        Text(model.setupMode == .join ? "JOIN RIDE" : "START RIDE")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(RideMeshTheme.darkTextOnAccent)
                            .frame(maxWidth: .infinity, minHeight: compactHeight ? 54 : 58, maxHeight: compactHeight ? 54 : 58)
                            .background(RideMeshTheme.accent)
                            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    .buttonStyle(.plain)
                    .padding(.top, compactHeight ? 16 : 22)

                    Text("No button is needed while riding • normal voice mode is hands-free.")
                        .font(.system(size: 10.5))
                        .foregroundStyle(RideMeshTheme.faint)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 10)
                        .padding(.bottom, 14)
                }
                .frame(width: contentWidth)
                .frame(maxWidth: .infinity)
                .padding(.top, compactHeight ? 2 : 6)
                .frame(minHeight: geometry.size.height, alignment: .top)
            }
            .scrollDismissesKeyboard(.interactively)
            .contentShape(Rectangle())
            .onTapGesture {
                focusedField = nil
            }
        }
        .background(RideMeshBackground())
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focusedField = nil }
            }
        }
    }

    private var setupHeader: some View {
        HStack(spacing: 0) {
            Button {
                focusedField = nil
                model.returnHome()
            } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(RideMeshTheme.white)
                    .frame(width: 52, height: 44)
            }
            .buttonStyle(.plain)

            VStack(spacing: 2) {
                Text("RIDE LOBBY")
                    .font(RideMeshTheme.condensed(18, weight: .bold))
                    .tracking(1.44)
                    .foregroundStyle(RideMeshTheme.white)
                Text(model.setupMode.rawValue)
                    .font(.system(size: 8.5, weight: .bold))
                    .foregroundStyle(RideMeshTheme.accent)
            }
            .frame(maxWidth: .infinity)

            Color.clear.frame(width: 52, height: 1)
        }
        .frame(height: 52)
    }

    private var riderPanel: some View {
        VStack(alignment: .leading, spacing: 0) {
            fieldLabel("YOUR NAME")

            TextField("Rider name", text: $model.riderName)
                .keyboardType(.default)
                .textContentType(.name)
                .textInputAutocapitalization(.words)
                .autocorrectionDisabled(true)
                .submitLabel(.next)
                .foregroundStyle(RideMeshTheme.white)
                .font(.system(size: 17))
                .focused($focusedField, equals: .name)
                .frame(height: 52)
                .onChange(of: model.riderName) { value in
                    if value.count > 18 { model.riderName = String(value.prefix(18)) }
                }
                .onSubmit { focusedField = .rideCode }

            Rectangle().fill(RideMeshTheme.accent).frame(height: 1)

            fieldLabel("RIDE CODE")
                .padding(.top, 12)

            TextField("RM2815 • minimum 5 characters", text: $model.rideCode)
                .keyboardType(.asciiCapable)
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled(true)
                .submitLabel(.next)
                .foregroundStyle(RideMeshTheme.white)
                .font(.system(size: 19, weight: .bold))
                .focused($focusedField, equals: .rideCode)
                .frame(height: 52)
                .onChange(of: model.rideCode) { value in
                    model.rideCode = String(RideMeshSignalingService.sanitizeRideCode(value).prefix(12))
                }
                .onSubmit { focusedField = .phone }

            Rectangle().fill(RideMeshTheme.accent).frame(height: 1)

            fieldLabel("PHONE NUMBER (OPTIONAL)")
                .padding(.top, 12)

            TextField("+91 98765 43210", text: $model.phoneNumber)
                .keyboardType(.phonePad)
                .textContentType(.telephoneNumber)
                .submitLabel(.done)
                .foregroundStyle(RideMeshTheme.white)
                .font(.system(size: 17, weight: .semibold))
                .focused($focusedField, equals: .phone)
                .frame(height: 50)
                .onChange(of: model.phoneNumber) { value in
                    let clean = RideMeshViewModel.sanitizePhone(value)
                    if clean != value { model.phoneNumber = clean }
                }
                .onSubmit { focusedField = nil }

            Text("Shared only with riders in this active RideMesh group for Call / Message actions. Include country code for WhatsApp.")
                .font(.system(size: 8.5, weight: .medium))
                .foregroundStyle(RideMeshTheme.faint)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 4)

            Rectangle().fill(RideMeshTheme.accent).frame(height: 1).padding(.top, 10)

            HStack(spacing: 12) {
                RMOutlinedAction(
                    title: "SHOW QR",
                    symbol: "qrcode",
                    iconColor: RideMeshTheme.white,
                    textColor: RideMeshTheme.white,
                    strokeColor: RideMeshTheme.border,
                    radius: 12,
                    height: 50,
                    fontSize: 11
                ) {
                    focusedField = nil
                    model.showQR = true
                }

                RMOutlinedAction(
                    title: "SCAN QR",
                    symbol: "qrcode.viewfinder",
                    iconColor: RideMeshTheme.white,
                    textColor: RideMeshTheme.white,
                    strokeColor: RideMeshTheme.border,
                    radius: 12,
                    height: 50,
                    fontSize: 11
                ) {
                    focusedField = nil
                    model.showScanner = true
                }
            }
            .padding(.top, 14)
        }
        .padding(18)
        .rmPanel(radius: 16)
    }

    private func audioRoutePanel(compact: Bool) -> some View {
        VStack(spacing: 0) {
            ForEach(RideAudioRoute.allCases) { route in
                Button { model.chooseAudioRoute(route) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: model.audioRoute == route ? "largecircle.fill.circle" : "circle")
                            .font(.system(size: 20))
                            .foregroundStyle(model.audioRoute == route ? RideMeshTheme.accent : RideMeshTheme.muted)
                        Text(route.title)
                            .font(.system(size: compact ? 12.5 : 13))
                            .foregroundStyle(RideMeshTheme.white)
                            .lineLimit(2)
                            .minimumScaleFactor(0.82)
                        Spacer(minLength: 0)
                    }
                    .frame(maxWidth: .infinity, minHeight: compact ? 42 : 46, alignment: .leading)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, compact ? 7 : 10)
        .rmPanel(radius: 16)
    }

    private var batteryPanel: some View {
        Toggle(isOn: $model.batterySaver) {
            Text("Battery Smart\nReduces background work while keeping voice responsive")
                .font(.system(size: 12.5))
                .foregroundStyle(RideMeshTheme.white)
                .lineSpacing(2)
        }
        .tint(RideMeshTheme.accent)
        .onChange(of: model.batterySaver) { _ in model.persist() }
        .padding(.horizontal, 14)
        .frame(minHeight: 66)
        .rmPanel(radius: 16)
    }

    private func fieldLabel(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .bold))
            .foregroundStyle(RideMeshTheme.faint)
    }
}
