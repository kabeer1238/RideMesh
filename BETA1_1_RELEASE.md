# RideMesh Beta 1.1

Version: `0.4.2-beta1.1` (`versionCode 12`)

## Focus
Beta 1.1 is a reliability, presentation and tester-experience update for the invited field-test group.

## Included
- Proper adaptive Android launcher icon using the chosen RideMesh artwork.
- App label standardized to `RideMesh`.
- Short, subtle logo splash before Home.
- New polished landing page with clear Create Ride / Join Ride actions, live readiness status, and quick Hybrid / Helmet / Smart Power indicators.
- Fixed the confirmed Internet packet header-size bug: 33 bytes, not 37.
- Added a regression test for exact Internet packet framing / PCM round-trip.
- Internet reconnect now uses short exponential backoff plus jitter instead of a synchronized fixed 2-second loop.
- Android backup is disabled for the Beta app data.
- Existing hands-free audio, AEC/NS/AGC where supported, adaptive VAD, wind-rumble filter, bounded playback queue, Battery Smart, QR/share invites, live Internet invite scanning and automatic Internet/local reconnect are retained.

## Deferred intentionally
- Internet room authentication and E2E encryption remain deferred for the small trusted Beta group.
- Opus and production relay infrastructure remain Beta 2 targets.
- Moving the complete live communication engine from MainActivity into RideService remains a major lifecycle hardening task for Beta 2; Beta 1.1 must still be field-tested with screen-off/OEM battery management.

## Tester priorities
1. 3-6 rider Internet calls.
2. 30-60 minute screen-off rides.
3. Network loss, complete outage and later 4G/5G recovery.
4. Local-range loss and rediscovery.
5. Different Bluetooth helmet/intercom brands.
6. Wind/noise and overlapping speech.
7. Battery consumption.
8. Launcher icon appearance and landing-page readability on different Android phones.
