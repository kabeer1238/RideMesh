import SwiftUI

struct RiderProfileView: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @FocusState private var nameFocused: Bool

    var body: some View {
        GeometryReader { geometry in
            let compactHeight = geometry.size.height < 760
            let horizontal = geometry.size.width >= 430 ? CGFloat(24) : CGFloat(18)
            let contentWidth = min(geometry.size.width - (horizontal * 2), CGFloat(520))

            ScrollView(showsIndicators: false) {
                VStack(spacing: 0) {
                    Image("RideMeshLogoExact")
                        .resizable()
                        .scaledToFit()
                        .frame(maxWidth: compactHeight ? 226 : 252)
                        .frame(height: compactHeight ? 72 : 84)
                        .padding(.top, compactHeight ? 8 : 16)

                    Text("WELCOME TO RIDEMESH")
                        .font(RideMeshTheme.condensed(compactHeight ? 24 : 27, weight: .bold))
                        .tracking(1.4)
                        .foregroundStyle(RideMeshTheme.white)
                        .multilineTextAlignment(.center)
                        .padding(.top, compactHeight ? 18 : 24)

                    Text("Choose the name your riding group will see. No account, password, OTP or verification is required.")
                        .font(.system(size: 12.5))
                        .foregroundStyle(RideMeshTheme.muted)
                        .lineSpacing(3)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 20)
                        .padding(.top, 9)

                    VStack(alignment: .leading, spacing: 0) {
                        Text("RIDER NAME")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(RideMeshTheme.faint)

                        TextField("Your name", text: $model.riderName)
                            .keyboardType(.default)
                            .textContentType(.name)
                            .textInputAutocapitalization(.words)
                            .autocorrectionDisabled(true)
                            .submitLabel(.done)
                            .foregroundStyle(RideMeshTheme.white)
                            .font(.system(size: 18, weight: .semibold))
                            .focused($nameFocused)
                            .frame(height: 54)
                            .onChange(of: model.riderName) { value in
                                if value.count > 18 { model.riderName = String(value.prefix(18)) }
                            }
                            .onSubmit {
                                nameFocused = false
                                model.saveRiderProfile()
                            }

                        Rectangle().fill(RideMeshTheme.accent).frame(height: 1)

                        Button {
                            nameFocused = false
                            model.saveRiderProfile()
                        } label: {
                            Text("SAVE & CONTINUE")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(RideMeshTheme.darkTextOnAccent)
                                .frame(maxWidth: .infinity, minHeight: compactHeight ? 54 : 58)
                                .background(RideMeshTheme.accent)
                                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                        .padding(.top, compactHeight ? 17 : 22)
                    }
                    .padding(compactHeight ? 16 : 18)
                    .rmPanel(radius: 18)
                    .padding(.top, compactHeight ? 20 : 26)

                    Text("Your rider name is stored on this iPhone and can be changed later in Settings.")
                        .font(.system(size: 10.5))
                        .foregroundStyle(RideMeshTheme.faintPlus)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                        .padding(.top, 13)
                        .padding(.bottom, 20)
                }
                .frame(width: contentWidth)
                .frame(maxWidth: .infinity)
                .frame(minHeight: geometry.size.height, alignment: .top)
            }
            .scrollDismissesKeyboard(.interactively)
            .contentShape(Rectangle())
            .onTapGesture { nameFocused = false }
        }
        .background(RideMeshBackground())
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { nameFocused = false }
            }
        }
        .onAppear {
            if model.riderName == "Rider" { model.riderName = "" }
            nameFocused = model.riderName.isEmpty
        }
    }
}
