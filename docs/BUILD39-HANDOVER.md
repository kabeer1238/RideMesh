# Android 39 / iOS 37 field candidate

Android 39 adds automatic transport handover and addresses offline audio discontinuities.
iOS 37 fixes Settings navigation; its voice feature remains online-only.
Neither build is a verified mixed Internet/offline gateway or a verified eight-phone intercom.

## Android operation

Settings > Voice connection defaults to Automatic on the first build-39 launch, including upgrades.
Internet voice only and Android offline only remain available for controlled tests.
Keep Wi-Fi and Bluetooth enabled, grant microphone/Nearby permissions, and use the same ride code.

Automatic uses Android's INTERNET + VALIDATED capabilities. On loss, a 2-second debounce
precedes local startup; return requires 8 seconds of continuous validation. The watchdog adds
up to its polling interval; peer discovery/WebRTC reconnection adds further interruption.
It does not promise seamless, zero-loss handover. A Wi-Fi network with no Internet is offline.
Validated Internet can still have an unreachable signaling service: this first policy does not
probe broker reachability or guarantee connectivity to the other rider. Phones can select
different paths if only one loses Internet. Mixed-route gateway bridging is not enabled.

The existing native InternetNode audio implementation is unchanged; one read-only interruption
accessor is added and checked separately by the baseline verifier. Handover releases
the outgoing engine and waits for microphone release before starting the incoming engine.
Mute, route selection and ride code are preserved. End Ride invalidates delayed handover work.

Offline changes: four bounded in-flight payloads per peer; six pending frames per speaker
with 120-ms expiry and round-robin fairness; paced 20-ms capture instead of pre-roll bursts;
400-ms VAD hangover; 60–120-ms playout priming; re-prime after starvation; monotonic timing;
and speaker buffer disposal on transport exit. Added rebuffer count to diagnostics.

Also see AUDIO-NONREGRESSION.md for call priority, microphone isolation, offline music ducking,
Bluetooth recovery and the physical-device acceptance gates added from the recovered specification.

Settings editors return to Settings on Save/Cancel/Back. iOS audio routing opens above Settings,
and Edit Name keeps the user inside Settings. Original iOS voice/services/ViewModel unchanged.

## Required phone validation

1. Install Android 39 on both Android phones. Select Internet only; verify two-way voice first.
2. Select Android offline only, keep Wi-Fi/Bluetooth on, disable Internet access, and verify
   quiet/loud speech, word beginnings/endings, simultaneous speech and a 2-second test tone.
3. Select Automatic on both. Start online, remove Internet from both without disabling radios,
   wait for local reconnection, restore Internet to both, and verify online reconnection.
4. Flap connectivity briefly; ensure no repeated switches. Repeat while muted, then unmute.
5. End Ride during handover; verify microphone indicator clears and delayed work does not restart it.
6. Test Settings name/phone/email/connection changes, including Cancel and Back; remain in Settings.
7. Then test headset routes, locked screen, incoming call recovery, three phones and larger groups.

Record direct links, send failures, audio drops, decoded packets, rebuffers and playback errors
before/after a 60-second sample. CI verifies compilation and policy/queue tests, not audible quality,
RF range, physical route changes, or background reliability.

References:
- https://developer.android.com/develop/connectivity/network-ops/reading-network-state
- https://developers.google.com/nearby/connections/android/exchange-data
