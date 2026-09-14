# Android vc40 / iOS vc38 — incremental field test

Baseline: 3ff95aaa44edc223fd5db42604da3e619a2d7c47 (Android vc39, iOS vc37).
Only offline-mesh-v1 is updated. Production is not modified.

## Android
- Offline PCM mixer no longer divides voice by all received frames (including silent riders).
- Frame-wide peak limiting avoids integer wrap/clipping on overlapping speech.
- Quiet syllables are retained; no new amplitude-only speech gate or talker selection.
- Five unit tests cover silence dilution, quiet speech, overlapping speech, waveform limiting and malformed/short frames.
- Original InternetNode is unchanged. Billing remains absent in the test APK.
- Existing automatic transport policy is unchanged: OS-validated Internet, 2-second outage debounce, 8-second recovery debounce, plus watchdog scheduling delay.
- Automatic mode is whole-device switching, NOT simultaneous Internet/offline bridging.
- Does not remove the existing online rider cap or establish tested 14-rider capacity.

## iOS
- Online-only voice retained; offline Hybrid sources remain excluded.
- Mute and End are large side-by-side controls below live status and ride code.
- Both Settings support links now email salesautopilotindia@gmail.com.
- Original online voice, interruption policy, signaling and view model are unchanged.

## Required phone validation (not established by CI)
1. Two Android phones: voice in both directions, quiet syllables and overlapping speech.
2. Six Android phones: one speaker with five quiet riders, then overlapping speech.
3. Automatic mode: lose Internet and recover; keep the same ride code on both phones.
4. Cellular/VoIP call interruption: intercom stays silent and resumes without rejoining. Private audio must never enter the group.
5. Music and Bluetooth route changes, Settings changes without navigation reset.
6. iOS small/large screen layout, support email and mute/end behavior.

CI compilation does not prove voice quality, call privacy, riding range or six-rider multihop performance.
Wind-noise-aware active-speaker processing, broader group capacity and true hybrid bridging remain separate work.
