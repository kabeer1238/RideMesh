# RideMesh Wi-Fi Aware discovery test

This package is build 29. It adds the first offline-connectivity checkpoint to the existing RideMesh iOS app: system Wi-Fi Aware pairing and nearby service discovery.

It does not move live WebRTC voice to Wi-Fi Aware yet. A successful pairing test is required before that next implementation step because Android-to-iPhone Wi-Fi Aware compatibility depends on the actual Android hardware and firmware.

## Build

1. Open Terminal at this folder.
2. Run `xcodegen generate`.
3. Open `RideMeshIOS.xcodeproj` in Xcode 26.
4. Select the iPhone 17 Pro Max and build.

If Xcode asks to add a Wi-Fi Aware capability, enable it for the RideMesh App ID and regenerate the provisioning profile. The declared service is `_ridemesh._tcp`.

## Test on iPhone

1. Keep mobile data, Wi-Fi hotspot, and internet off on both phones.
2. Open RideMesh > Settings > Offline Discovery.
3. Tap **Make This iPhone Discoverable** and allow the Apple system pairing screen.
4. The Android test build will need to publish the same `_ridemesh._tcp` Wi-Fi Aware service.
5. Tap **Find Nearby RideMesh Peers** and record whether the POCO appears.

The result of this build tells us whether the phones can form the direct physical link required for offline RideMesh voice.
