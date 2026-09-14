# Android vc41 — experimental Silero VAD

Baseline: Android vc40 commit f4bcf83c83d69ab6f6f408022e56e5de90f12589.
Branch: offline-mesh-v1. Production is not modified.

- Optional Silero ONNX speech detector for Android offline audio only.
- Disabled by default. Toggle Settings > SILERO AI VAD, then restart offline audio.
- 16 kHz PCM is sequentially chunked into 512-sample windows; Opus remains 20 ms.
- Original adaptive energy/echo detector remains the startup/error fallback.
- During remote playout, the prior echo-energy guard is retained in addition to Silero.
- Private call isolation, mute pre-roll clearing, online WebRTC, transport switching and iOS are unchanged.
- Diagnostics show Silero decisions, active state, average and maximum inference time.
- Adds pinned android-vad Silero 2.0.10 / ONNX dependency and third-party notices.

Required field comparison: same two Android devices and ride code, 60 seconds each with Silero OFF
and ON: quiet speech, engine/wind noise, simultaneous speech, music ducking, and call interruption.
CI cannot establish speech accuracy, privacy, riding range, latency or multihop performance.
