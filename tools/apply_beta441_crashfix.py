from pathlib import Path

ROOT = Path('.')

# MainActivity: initialize the media engine before starting the foreground service.
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()
old = '''        try {\n            stopLobbyDiscovery()\n            startRideServiceSafely()\n\n            rideStarted = true\n            directPeerCount = 0\n            internetPeerCount = 0\n            meshRunning = false\n            internetConnectedSinceMs = 0L\n            lastMeshRefreshMs = 0L\n\n            // Beta4 voice is captured and rendered directly by WebRTC. The old PCM\n            // AudioEngine stays idle so it cannot create a second microphone/audio path.\n            internetNode.start(code, rider, deviceLabel())\n            internetNode.setMuted(micMuted)\n            applySelectedAudioRoute()\n\n            binding.activeRideCode.text = code\n'''
new = '''        try {\n            stopLobbyDiscovery()\n\n            rideStarted = true\n            directPeerCount = 0\n            internetPeerCount = 0\n            meshRunning = false\n            internetConnectedSinceMs = 0L\n            lastMeshRefreshMs = 0L\n\n            // Initialize voice first. If a device rejects audio/WebRTC initialization, the\n            // existing recovery path keeps the Activity alive instead of leaving an FGS behind.\n            internetNode.start(code, rider, deviceLabel())\n            internetNode.setMuted(micMuted)\n            applySelectedAudioRoute()\n\n            // Start the foreground ride service only after media initialization succeeds.\n            startRideServiceSafely()\n\n            binding.activeRideCode.text = code\n'''
if old not in s:
    raise SystemExit('startRideNow crash-fix anchor not found')
s = s.replace(old, new, 1)
p.write_text(s)

# Internet voice: retain only the signaling-side fast-presence benefit from Beta4.4.
# Restore the more conservative media/JNI values from the earlier field-test engine.
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt'
i = p.read_text()
i = i.replace('audioJitterBufferMaxPackets = 30', 'audioJitterBufferMaxPackets = 50')
i = i.replace('iceCandidatePoolSize = 4', 'iceCandidatePoolSize = 2')
i = i.replace('pc.setBitrate(24_000, 48_000, 80_000)', 'pc.setBitrate(24_000, 40_000, 64_000)')
i = i.replace(';maxaveragebitrate=48000;usedtx=0', '')
i = i.replace('if (!fmtp.contains("maxaveragebitrate=", ignoreCase = true)) fmtp += ";maxaveragebitrate=48000"\n            if (!fmtp.contains("usedtx=", ignoreCase = true)) fmtp += ";usedtx=0"\n', '')
i = i.replace('private const val SOCKET_TIMEOUT_MS = 1_000', 'private const val SOCKET_TIMEOUT_MS = 3_000')
i = i.replace('private const val PRESENCE_TIMEOUT_MS = 8_000L', 'private const val PRESENCE_TIMEOUT_MS = 14_000L')
i = i.replace('private const val OFFER_RETRY_INTERVAL_MS = 1_500L', 'private const val OFFER_RETRY_INTERVAL_MS = 2_000L')
i = i.replace('private const val ICE_DISCONNECTED_GRACE_MS = 3_000L', 'private const val ICE_DISCONNECTED_GRACE_MS = 6_000L')
i = i.replace('private const val ICE_FAILED_RETRY_MS = 600L', 'private const val ICE_FAILED_RETRY_MS = 1_000L')
i = i.replace('private const val RECONNECT_BASE_DELAY_MS = 500L', 'private const val RECONNECT_BASE_DELAY_MS = 1_000L')
i = i.replace('private const val RECONNECT_MAX_DELAY_MS = 4_000L', 'private const val RECONNECT_MAX_DELAY_MS = 8_000L')
i = i.replace('private const val RECONNECT_JITTER_MS = 250L', 'private const val RECONNECT_JITTER_MS = 500L')
# Keep PRESENCE_INTERVAL_MS at 1 second and the immediate newcomer response: these are
# signaling-only optimizations and do not touch the native media stack.
p.write_text(i)

print('Beta4.4.1 crash-fix patch applied')
