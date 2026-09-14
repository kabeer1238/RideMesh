# Audio recovery test: Android 37 / iOS 35

## Evidence from the previous device test

On shared Wi-Fi, Android 36 captured and sent 11,162 audio packets. iOS 34
received 11,698 and decoded 2,352 but reported audio engine off, zero microphone
buffers, and AVFAudio error 2003329396. Neither user heard voice. Counts were
recorded at different moments. This proves packet reception and decoding, not
audible playback or router-free discovery.

## Changes

- iOS route recovery changes input/output selection only when needed. Cancelled
  route tasks exit, preventing repeated route mutations after notifications.
- The iOS mixer converts the 16 kHz network stream to the hardware output format.
- Failed or stalled voice processing switches to standard input/output for the
  rest of the ride. This compatibility mode lacks the engine's echo cancellation;
  use headphones when assessing full-duplex quality. The output route is preserved.
- Retry budget resets only after actual microphone callbacks. Failed-start errors
  include stage, domain and code. Engine, capture and rendered sample counts
  distinguish decoding from output activity; they do not prove audibility.
- iOS Voice status no longer claims Ready from a network connection. Test tone is
  disabled while the engine is stopped. Readiness requires capture callbacks.
- Android microphone status clears after stream failure. Speaker writes handle
  partial writes and rebuild a failed AudioTrack; diagnostics expose playback
  errors and PCM bytes written. A tone replaces microphone packets for two seconds
  instead of overloading a single audio sequence with both streams.
- Android Internet-only mode opens Internet status, avoiding misleading stopped
  mesh diagnostics. Existing transport preferences and wire formats are retained.

## Install

Android: extract the artifact and install RideMesh-hybrid8-vc37-debug.apk. This is
the separate no-billing test app, not the production Play Store package.

iOS: extract the artifact, then extract RideMesh-iOS-vc35-Hybrid8-source.zip. In
the directory containing project.yml run `xcodegen generate`, then
`open RideMeshIOS.xcodeproj`. Select your signing team and iPhone and Run. The
UNSIGNED archive cannot be installed directly.

## First device check

1. End the ride on both phones. Select Hybrid on both and BLE-only test OFF.
2. Keep Wi-Fi and Bluetooth on; use the same Wi-Fi and same ride code.
3. Confirm 2 riders and 1 local link. Check iOS engine ON and growing mic buffers.
4. Send the tone from Android, listen on iPhone; then reverse the direction.
5. Speak in both directions. Reopen Android Status and photograph both statuses.
6. Test original Internet voice separately with Hybrid off / Internet-only on both.

After shared-Wi-Fi voice passes, test with the router's internet uplink removed
while keeping its Wi-Fi active, then test without a shared router. These are
different tests. BLE-only remains an experimental discovery isolation option.

## Validation boundary

CI compiles both apps, runs Android codec/routing tests and iOS routing/recovery
policy tests. Physical microphones, speakers, headsets, direct offline discovery,
range and eight-rider voice still require device validation. The previous logo
margin masks remain in place. Production branch is not changed.
