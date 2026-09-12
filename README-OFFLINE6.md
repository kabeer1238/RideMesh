# RideMesh Cyan UI — six-rider offline test source (vc32)

STATUS: GitHub Actions has passed the Android unit tests and built a signed debug APK. Download the latest successful offline-mesh-v1 workflow artifact. Physical six-phone testing is still required.

## What this package contains
The vc31 Cyan UI resources are unchanged. The September 11 source supplies the Opus codec, RME1 packet envelope, relay router, Nearby transport and hotspot reference classes. The active Android path is Nearby P2P_CLUSTER; hotspot and iPhone connectivity are not enabled.

Changes for this test:
- Offline mode and A–F forced-chain roles exposed in Settings; NORMAL remains automatic nearby connections.
- Removed the one-connection discovery restriction. Up to five direct neighbors can be accepted/requested.
- Relayed presence distinguishes reachable riders from direct links. Presence expires after approximately eight seconds.
- RME1 TTL=4 allows the initial transmission plus four forwards: five links across six riders. Duplicate suppression and previous-hop checks bound flooding.
- Per-peer queues keep one pending frame per speaker (up to six), with 140 ms local queue expiry. Completion uses Nearby transfer callbacks, with a stalled-transfer timeout.
- Opus remains 16 kHz mono, 20 ms, target 32 kbps, using the source project's com.plasmoverse:concentus:1.0.0 dependency.
- Encoded packets enter the per-speaker jitter buffer before Opus decoding. Missing frames request Opus concealment. Local playout queue is bounded to six frames (120 ms); packets waiting locally over 140 ms are discarded.
- New per-ride identities avoid sequence-reset collisions on rejoin.
- The Google Billing SDK dependency is removed. The testing billing adapter does not connect to Google Play or show checkout. No subscription is needed in this package.

The compiled-code bridge considered earlier is NOT included. Codec source/dependency wiring now comes from the September 11 ZIP.

## Build in Android Studio
1. Extract this ZIP into a NEW folder. Open the folder containing settings.gradle.kts.
2. Allow Gradle sync and Android SDK installation. Use JDK 17 or the compatible embedded Android Studio Gradle JDK.
3. Select the debug build variant.
4. In the project terminal on Windows run:

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug
```

Expected output AFTER a successful build:

```text
app/build/outputs/apk/debug/RideMesh-offline6-vc32-debug.apk
```

Debug application ID: in.autopilotindia.ridemesh.offline
Version name: 1.0.3-offline6-test
Version code: 32

It installs separately from the production Play app. It can replace an older .offline install only if signed with the same debug key. A signature mismatch requires removing the old test app (which removes its local test data) or using the original signing key.

Maps keys remain supplied by MAPS_API_KEY; map setup is separate from offline voice. Do not submit this billing-free test package to production. When integrating into your existing Git repository, use offline-mesh-v1 and leave production-vc25-billing8 alone.

## Six-phone test
Start with two phones on NORMAL, then three with A/B/C, then six with A/B/C/D/E/F. Use the same build and ride code on every phone.

Turn OFF mobile data and disconnect from an internet Wi-Fi network. Keep Wi-Fi and Bluetooth ON. Grant microphone, Nearby and requested location permissions; enable location services if discovery requires them. No router is required for the intended Nearby path. Begin stationary, using headphones to avoid room feedback.

Settings > Voice connection > Offline mesh.
Settings > Offline test role > assign one unique role per phone.

| Role | Allowed direct neighbors | Expected direct links in six-phone test |
|---|---|---:|
| A | B | 1 |
| B | A, C | 2 |
| C | B, D | 2 |
| D | C, E | 2 |
| E | D, F | 2 |
| F | E | 1 |

All six should appear after presence propagates. Speak A to F and F to A, then from every other rider. A–F end-to-end delivery requires five links. Verify diagnostics, not just that six phones are nearby.

Check mute (relay/listening remain active), screen off, headset route, one and two simultaneous speakers, then all six. Remove a middle phone: a pure chain MUST split. Rejoin it and verify recovery. Test NORMAL topology separately with an alternate route available.

No radio range, simultaneous-six-speaker quality, riding performance or Android–iPhone interoperability is verified by this source package. Each hop adds radio and scheduling delay; queue limits are not an end-to-end latency guarantee. RTT diagnostics describe direct links, not mouth-to-ear latency.

## Validation performed
- Java routing-policy and real audio-queue checks compiled/executed successfully: six-source chain/ring, partition, alternate route, TTL, lab isolation, per-speaker fairness, stale-frame rejection and queue bound.
- All XML parsed successfully; all 43 Cyan UI resource files match the supplied vc31 source byte-for-byte.
- Source checks confirm offline decode callback wiring and absence of Billing SDK imports/dependency or a premium-screen navigation call.
- GitHub Actions passed testDebugUnitTest, including the actual Kotlin relay router and Opus tests, and assembleDebug. Initial successful run: https://github.com/kabeer1238/RideMesh/actions/runs/34662729042.
- Local Gradle dependency downloads were unavailable; the successful compilation and tests ran on GitHub Actions.
- No physical phone tests performed.

## Restoring billing later
The production-vc25-billing8 branch retains the production billing implementation. Restoring it also requires restoring the billing dependency, entitlement checks and subscription UI navigation. Do not enable billing by changing only one boolean.
