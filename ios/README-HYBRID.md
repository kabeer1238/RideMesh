# Android 38 / iOS 36: original online voice and separate Android offline

The user's September 14 request replaces hybrid development with independent
online and Android-to-Android offline modes. iPhone-to-iPhone remains ONLINE,
as requested. Android-to-iPhone offline bridging is paused.

## Online source restored

Android InternetNode.kt is restored byte-for-byte from the supplied vc31 Cyan UI
source. iOS WebRTCVoiceService.swift, AudioSessionManager.swift,
RideMeshSignalingService.swift and RideMeshViewModel.swift are restored byte-for-byte
from the supplied pre-hybrid RideMeshIOS-v1.3-WiFiAware-No-Subscription source.
The iOS WebRTC dependency is restored to that source's 151.0.0 version.

tools/online-baseline.sha256 pins these files. Both CI builds verify the hashes.
This does not assert phone performance: the original online call still needs a
device regression test. Production-vc25-billing8 is not modified.

## Modes

- Android defaults to Internet Voice on upgrade. Online voice uses native WebRTC.
- Android Settings > Voice Connection > Android-to-Android offline starts only the
  Nearby P2P_CLUSTER / Opus audio path. No internet voice engine or gateway starts.
- Android offline advertises on its own service, using all normal Nearby media.
  Old BLE-only preferences are ignored. Both Android devices need build 38.
- Offline lab role defaults to NORMAL on upgrade. Leave it there for two-phone
  testing; chain roles are only for later controlled relay tests.
- iOS starts only the restored online voice service. Hybrid code is excluded from
  the app target and Nearby/Opus hybrid dependencies are removed. The older
  experimental sources remain in the repository for reference, not in the app.
- Existing logo rendering cleanup and billing-free testing remain.

## Install and test

Android: install RideMesh-android-vc38-debug.apk on BOTH Android phones.
iOS: extract the source ZIP inside the artifact. In the folder with project.yml,
run `xcodegen generate`, open RideMeshIOS.xcodeproj, select your signing team and
iPhone, then Run. The unsigned app archive cannot install directly.

1. Test Internet Voice first using the same ride code and working internet on
   both phones. Test Android/Android and iPhone/iPhone where two phones are
   available. The restored online protocol also remains shared across platforms.
2. End rides on both Android phones, select Android-to-Android offline, then use
   the same ride code. Keep Bluetooth and Wi-Fi ON; disable mobile data. Start
   nearby with both apps in the foreground. Grant requested Nearby permissions.
3. Check for 2 riders / 1 direct link. Speak each direction and send the test tone.
   Reopen Status on both to capture fresh microphone, received, decoded, and
   speaker-write counts.
4. Record whether phones share a Wi-Fi router. Shared-Wi-Fi success does not prove
   router-free discovery. Test without a shared access point after voice works.
5. Expand to three phones / one relay only after two-phone bidirectional voice
   passes, then expand to six and eight riders.

No physical voice, router-free discovery, range, or multihop result is claimed
from CI. CI verifies compilation, the original online file hashes, and Android
codec/routing tests. Retained Swift protocol tests concern the offline library;
they are not tests of the online iPhone app's microphone or speakers.
