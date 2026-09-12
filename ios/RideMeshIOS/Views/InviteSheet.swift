import SwiftUI

struct InviteSheet: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            RideMeshBackground()
            VStack(spacing: 0) {
                RMModalHeader(title: "INVITE RIDERS") { dismiss() }

                VStack(alignment: .leading, spacing: 0) {
                    Text("Current code")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(RideMeshTheme.faint)
                    Text(model.normalizedRideCode)
                        .font(RideMeshTheme.condensed(32, weight: .bold))
                        .tracking(1.5)
                        .foregroundStyle(RideMeshTheme.accent)
                        .padding(.top, 6)
                    Text("Share this Ride Code or QR. Riders use Join a Ride and the same code to enter your group.")
                        .font(.system(size: 12))
                        .foregroundStyle(RideMeshTheme.muted)
                        .lineSpacing(2)
                        .padding(.top, 10)
                }
                .padding(18)
                .frame(maxWidth: .infinity, alignment: .leading)
                .rmPanel(radius: 16)
                .padding(.top, 14)

                Button {
                    dismiss()
                    DispatchQueue.main.async { model.showQR = true }
                } label: {
                    Text("SHOW QR CODE")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(RideMeshTheme.darkTextOnAccent)
                        .frame(maxWidth: .infinity, minHeight: 54)
                        .background(RideMeshTheme.accent)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                }
                .buttonStyle(.plain)
                .padding(.top, 16)

                ShareLink(item: model.inviteURL) {
                    Text("SHARE QR CODE")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(RideMeshTheme.white)
                        .frame(maxWidth: .infinity, minHeight: 54)
                        .overlay(RoundedRectangle(cornerRadius: 14).stroke(RideMeshTheme.border, lineWidth: 1))
                }
                .padding(.top, 10)

                if model.isRideActive {
                    Text("Your current Internet conversation continues while you invite.")
                        .font(.system(size: 11))
                        .foregroundStyle(RideMeshTheme.muted)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                        .padding(.top, 14)
                }

                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.top, 12)
        }
        .preferredColorScheme(.dark)
    }
}
