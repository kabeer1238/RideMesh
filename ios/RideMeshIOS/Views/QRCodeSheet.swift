import CoreImage.CIFilterBuiltins
import SwiftUI
import UIKit

struct QRCodeSheet: View {
    @EnvironmentObject private var model: RideMeshViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            RideMeshBackground()
            ScrollView(showsIndicators: false) {
                VStack(spacing: 0) {
                    RMModalHeader(title: "RIDE QR") { dismiss() }

                    Text("Current code")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(RideMeshTheme.faint)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 14)

                    Text(model.normalizedRideCode)
                        .font(RideMeshTheme.condensed(30, weight: .bold))
                        .tracking(1.4)
                        .foregroundStyle(RideMeshTheme.accent)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 4)

                    if let image = QRCodeGenerator.image(from: model.inviteURL.absoluteString) {
                        Image(uiImage: image)
                            .interpolation(.none)
                            .resizable()
                            .scaledToFit()
                            .padding(18)
                            .background(Color.white)
                            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .padding(.horizontal, 30)
                            .padding(.top, 18)

                        ShareLink(item: model.inviteURL) {
                            Text("SHARE QR")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(RideMeshTheme.darkTextOnAccent)
                                .frame(maxWidth: .infinity, minHeight: 54)
                                .background(RideMeshTheme.accent)
                                .clipShape(RoundedRectangle(cornerRadius: 14))
                        }
                        .padding(.top, 18)
                    }

                    Text("Share this Ride Code or QR. Riders use Join a Ride and the same code to enter your group.")
                        .font(.system(size: 11))
                        .foregroundStyle(RideMeshTheme.muted)
                        .multilineTextAlignment(.center)
                        .lineSpacing(2)
                        .padding(.horizontal, 12)
                        .padding(.top, 14)

                    if model.isRideActive {
                        Text("Your current Internet conversation continues while you invite.")
                            .font(.system(size: 10))
                            .foregroundStyle(RideMeshTheme.faintPlus)
                            .multilineTextAlignment(.center)
                            .padding(.top, 8)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)
                .padding(.bottom, 24)
            }
        }
        .preferredColorScheme(.dark)
    }
}

enum QRCodeGenerator {
    static func image(from string: String) -> UIImage? {
        let context = CIContext()
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(string.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 10, y: 10)),
              let cg = context.createCGImage(output, from: output.extent) else { return nil }
        return UIImage(cgImage: cg)
    }
}
