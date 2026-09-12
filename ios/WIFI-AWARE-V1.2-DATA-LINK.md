# RideMesh iOS v1.2 — Android-compatible Wi-Fi Aware data-link contract

This package keeps the v1.1 DeviceDiscoveryUI pairing screen and adds the byte-level protocol contract used by Android `WifiAwareWireProtocol.kt`.

Contract: `_ridemesh._tcp`, protocol v1, TCP 49355, `RMESH1` identity, 4-byte big-endian frame length, 1-byte frame type, HELLO=1, DATA=2, PING=3, PONG=4. Ride tokens are the first 8 bytes (16 lowercase hex chars) of SHA-256 of the trimmed uppercased ride code.

The required Wi-Fi Aware entitlement is now included for both Publish and Subscribe. Build number is normalized to 30.

Important: the Apple system pairing/data-path handshake and the Android NAN implementation must be proven on physical hardware before this can be called a production Android↔iPhone link. The next hardware milestone is pairing, secure data-path establishment, RMESH1 exchange, then PING/PONG RTT.
