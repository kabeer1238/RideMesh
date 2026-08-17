# RideMesh Product Roadmap

## Product goal
Universal motorcycle group voice that does not care which helmet intercom brand a rider owns.

## V0.2 — bench proof
- Phone-only PTT
- Nearby P2P_CLUSTER
- App-level multi-hop relay
- Phone / Auto / Helmet audio routing
- Hardware volume-button PTT
- Basic Android voice processing

## V0.3 — network reliability
- Move mesh/audio engine into foreground service
- Heartbeats and rider presence
- Reconnect/backoff logic
- Topology + hop diagnostics
- Sequence jitter buffer
- Packet loss metrics
- Secure connection verification

## V0.4 — efficient voice
- Opus encode/decode
- 20 ms frames
- Adaptive bitrate
- VAD / silence suppression
- Wind-noise-aware gate

## V0.5 — ride-ready controls
- Screen-off reliability
- Bluetooth/handlebar PTT input mapping
- Spoken connection status prompts
- Automatic route switching phone ↔ helmet
- Battery/thermal mode

## V0.6 — hybrid network
- Local mesh preferred
- Internet relay fallback when local mesh breaks
- Automatic handoff without user action
- Group membership synchronization

## V0.7 — open intercom
- Full duplex
- Echo management
- Active-speaker limits/mixing
- Per-rider mute
- Priority leader/SOS audio

## V1.0 — rider product
- QR / ride-code joining
- Encrypted private groups
- Rider roster + topology
- Optional live group radar
- SOS broadcast
- Voice history
- Diagnostics export
- Helmet compatibility matrix
- Field-tested reconnection and battery profile
