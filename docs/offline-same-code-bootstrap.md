# Offline same-code Android ↔ iPhone bootstrap

This test-only path keeps stable production untouched.

1. Android starts a `LocalOnlyHotspot`, Bonjour `_ridemesh._tcp`, and TCP port `49355`.
2. Android advertises the RideMesh BLE service UUID. Its scan response contains only the eight-byte SHA-256 ride-token fingerprint, never the hotspot password.
3. iPhone scans for the service and connects only when its locally calculated token matches.
4. The hotspot invite characteristic requires an encrypted, authenticated OS Bluetooth bond (`PERMISSION_READ_ENCRYPTED_MITM`). The phones can show a one-time system pairing confirmation.
5. iPhone applies the received temporary configuration with `NEHotspotConfigurationManager`.
6. Bonjour/TCP completes the `RMESH1` HELLO token validation and begins PING/PONG RTT measurement.
7. After repeated Bonjour failures, iPhone returns to BLE discovery so it can recover if Android recreated its hotspot with different credentials.

The existing QR payload remains available as a fallback.
