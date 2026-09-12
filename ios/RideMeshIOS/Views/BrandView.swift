import SwiftUI

struct RideMeshBrandView: View {
    var width: CGFloat = 218
    var height: CGFloat = 76

    var body: some View {
        Image("RideMeshLogoExact")
            .resizable()
            .scaledToFit()
            .frame(width: width, height: height, alignment: .leading)
            .accessibilityLabel("RideMesh by Autopilot India")
    }
}

struct RideMeshIconView: View {
    var size: CGFloat = 44

    var body: some View {
        Image("RideMeshIconExact")
            .resizable()
            .scaledToFit()
            .frame(width: size, height: size)
            .accessibilityLabel("RideMesh")
    }
}
