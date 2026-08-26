# RideMesh Beta5.2 vc20 — Clean Shutdown + Live Rider Map Reliability

APK-first field-test release. No AAB.

## Fixes

- Foreground ride service uses START_NOT_STICKY.
- Swiping RideMesh away from Android Recents is treated as an explicit close and releases the active ride runtime, microphone/audio path, live location updates, signaling/voice connections and foreground notification.
- Locking the phone, opening Maps/music/navigation, or normal backgrounding does not trigger this shutdown path.
- END RIDE continues to stop the full active ride cleanly.
- First live location received from each remote rider forces the map camera to refit, preventing valid remote markers from existing outside the current viewport.
- A newly detected rider triggers an immediate republish of the local cached position.
- Network/signaling recovery triggers a location republish.
- Stationary riders send a lightweight cached-location heartbeat every 5 seconds while location permission remains granted and the ride remains active.
- Map header reports how many rider positions are currently live.

## Google Maps

The workflow requires the `GOOGLE_MAPS_API_KEY` repository secret and fails instead of producing a map-disabled field-test APK when the secret is missing. The key itself remains outside source control.

## Test with the same vc20 APK on all map participants

Older RideMesh versions that predate the Live Rider Map cannot publish their location, so install vc20 on every phone used for the all-rider map test.
