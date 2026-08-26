# RideMesh Beta 1.1

Version: `0.4.3-beta1.1` (`versionCode 13`)

## Focus
Beta 1.1 is a reliability, rider-identity and presentation update for the invited field-test group.

## Included
- RideMesh chosen cyan/white artwork is used as the Android launcher icon with improved adaptive-icon sizing.
- Short black/cyan logo splash and the refined rider-focused landing page are retained.
- Connected rider roster: tap `RIDERS` during an active ride to see your own name/device plus connected riders by RideMesh user name and Android device model.
- The `RIDERS` button displays the current rider total.
- Internet presence now carries rider name + device model while keeping the original 24-byte UUID/timestamp prefix readable by older Beta clients.
- Local Nearby peers expose their advertised rider name and device model to the roster.
- Fixed Internet packet header-size bug: 33 bytes, not 37.
- Regression tests cover exact Internet audio framing, rider/device presence metadata and legacy 24-byte presence decoding.
- Internet reconnect uses short exponential backoff plus jitter.
- Android backup is disabled for Beta app data.
- Existing hands-free audio, AEC/NS/AGC where supported, adaptive VAD, wind-rumble filter, bounded playback queue, Battery Smart, QR/share invites, live Internet invite scanning and automatic Internet/local reconnect are retained.

## Roster behavior
- User-entered RideMesh rider name is preferred.
- Android manufacturer/model is shown below the rider name and acts as a fallback identity.
- Internet group riders are listed with `Internet` as the path.
- During local-only operation, directly connected Nearby peers are listed with `Local mesh` as the path.
- Older Beta clients that do not send identity metadata remain compatible, but may appear with a short fallback rider ID until everyone updates.

## Deferred intentionally
- Internet room authentication and E2E encryption remain deferred for the small trusted Beta group.
- Opus and production relay infrastructure remain Beta 2 targets.
- Moving the complete live communication engine from MainActivity into RideService remains a major lifecycle hardening task for Beta 2; Beta 1.1 must still be field-tested with screen-off/OEM battery management.

## Tester priorities
1. Install the same `0.4.3-beta1.1` build on all test phones.
2. Verify the RideMesh launcher icon in the app drawer/home screen.
3. Join 3-6 riders and confirm `RIDERS` shows each user/device correctly.
4. Test Internet calls and network loss/recovery.
5. Test local-range loss and rediscovery.
6. Test different Bluetooth helmet/intercom brands.
7. Test wind/noise, overlapping speech and battery consumption.
