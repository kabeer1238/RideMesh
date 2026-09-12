# vc20 implementation scope

This release intentionally preserves the existing proven voice architecture and focuses only on Android lifecycle cleanup and Live Rider Map reliability.

The foreground service remains active for normal background operation, screen lock, navigation and music. A deliberate Recents swipe is handled as an explicit close. Remote rider map positions are refit into view when their first live packet arrives, and active rides periodically republish a cached position at low frequency while stationary so new riders can become visible without requiring movement.
