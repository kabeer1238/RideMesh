from pathlib import Path

ROOT = Path('.')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# Version: vc20 / Beta5.2. Keep the vc19 map + vc18 voice/reliability baseline.
# -----------------------------------------------------------------------------
p = ROOT / 'app/build.gradle.kts'
s = p.read_text()
s = s.replace('versionCode = 19', 'versionCode = 20')
s = s.replace('versionName = "1.0.0-beta5.1-live-rider-map"', 'versionName = "1.0.0-beta5.2-clean-shutdown-map"')
p.write_text(s)


# -----------------------------------------------------------------------------
# Foreground Ride service: background/screen-off continues, but a deliberate
# Recents swipe stops the ride and Android must not resurrect it afterward.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/service/RideService.kt'
s = p.read_text()
s = s.replace('return START_STICKY', 'return START_NOT_STICKY')
if 'override fun onTaskRemoved(rootIntent: Intent?)' not in s:
    anchor = '    override fun onBind(intent: Intent?): IBinder? = null\n'
    block = '''    override fun onTaskRemoved(rootIntent: Intent?) {\n        // A Recents swipe is treated as an explicit app close. Release the\n        // Activity-owned voice/location runtime before this foreground service exits.\n        RideShutdownCoordinator.requestShutdown()\n        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)\n        stopSelf()\n        super.onTaskRemoved(rootIntent)\n    }\n\n    override fun onDestroy() {\n        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)\n        super.onDestroy()\n    }\n\n'''
    s = replace_once(s, anchor, block + anchor, 'RideService task removal cleanup')
p.write_text(s)


# -----------------------------------------------------------------------------
# MainActivity: register an explicit shutdown callback while a ride is active,
# clear it when END RIDE is used, and avoid UI work during task-removal cleanup.
# Also make remote map positions appear immediately and refit the camera when a
# rider's first live location arrives.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

if 'import com.bikemesh.ridemesh.service.RideShutdownCoordinator' not in s:
    s = s.replace(
        'import com.bikemesh.ridemesh.service.RideService\n',
        'import com.bikemesh.ridemesh.service.RideService\nimport com.bikemesh.ridemesh.service.RideShutdownCoordinator\n',
        1,
    )

if 'private val locationShareHeartbeat' not in s:
    anchor = '    private val speakingUntilMs = ConcurrentHashMap<String, Long>()\n'
    heartbeat = '''    private val locationShareHeartbeat = object : Runnable {\n        override fun run() {\n            if (!rideStarted) return\n            publishCachedLocalLocationIfDue(force = false)\n            mainHandler.postDelayed(this, LOCATION_SHARE_HEARTBEAT_CHECK_MS)\n        }\n    }\n\n'''
    s = replace_once(s, anchor, anchor + heartbeat, 'location heartbeat state')

# Register cleanup only after the full ride runtime (including map sharing) is alive.
if 'RideShutdownCoordinator.register(::shutdownRideRuntimeFromTaskRemoval)' not in s:
    anchor = '            beginLiveMapSession()\n'
    s = replace_once(
        s,
        anchor,
        anchor + '            RideShutdownCoordinator.register(::shutdownRideRuntimeFromTaskRemoval)\n',
        'register shutdown coordinator',
    )

# END RIDE should clear the retained shutdown callback before returning home.
if 'RideShutdownCoordinator.clear()\n        rideStarted = false' not in s:
    anchor = '        stopService(Intent(this, RideService::class.java))\n\n        rideStarted = false\n'
    s = replace_once(
        s,
        anchor,
        '        stopService(Intent(this, RideService::class.java))\n        RideShutdownCoordinator.clear()\n\n        rideStarted = false\n',
        'clear shutdown coordinator on stopRide',
    )

# Start/stop a very light cached-location heartbeat. Moving riders still publish
# from GPS callbacks; this only guarantees stationary riders/new joiners remain visible.
if 'mainHandler.post(locationShareHeartbeat)' not in s:
    anchor = '''        updateLiveMapHeader()\n        ensureLocationSharingPermission(promptIfMissing = true)\n    }\n\n    private fun endLiveMapSession() {\n'''
    replacement = '''        updateLiveMapHeader()\n        mainHandler.removeCallbacks(locationShareHeartbeat)\n        mainHandler.post(locationShareHeartbeat)\n        ensureLocationSharingPermission(promptIfMissing = true)\n    }\n\n    private fun endLiveMapSession() {\n        mainHandler.removeCallbacks(locationShareHeartbeat)\n'''
    s = replace_once(s, anchor, replacement, 'map heartbeat lifecycle')

# First location packet from a rider must force a group camera refit. In vc19 the
# first fit commonly happened while only YOU existed, leaving later remote markers
# outside the visible camera viewport.
old_callback = '''    override fun onInternetRiderLocation(location: InternetNode.RiderLocation) {\n        if (!rideStarted) return\n        riderLocations[location.riderId.toString()] = location\n        runOnUiThread {\n            updateLiveMapHeader()\n            if (liveMapVisible) renderLiveRiderMap(fitGroup = false)\n        }\n    }\n'''
new_callback = '''    override fun onInternetRiderLocation(location: InternetNode.RiderLocation) {\n        if (!rideStarted) return\n        val riderId = location.riderId.toString()\n        val firstLocationFromRider = riderLocations.put(riderId, location) == null\n        runOnUiThread {\n            updateLiveMapHeader()\n            if (liveMapVisible) {\n                if (firstLocationFromRider) lastMapFitMs = 0L\n                renderLiveRiderMap(fitGroup = firstLocationFromRider)\n            }\n        }\n    }\n'''
if new_callback not in s:
    s = replace_once(s, old_callback, new_callback, 'remote rider first-location camera fit')

# When a new rider becomes known, immediately republish our cached position rather
# than waiting for the next GPS movement callback.
old_peer_count = '''    override fun onInternetPeerCount(count: Int) {\n        internetPeerCount = count\n        runOnUiThread { updateTransportStatus() }\n    }\n'''
new_peer_count = '''    override fun onInternetPeerCount(count: Int) {\n        val previousCount = internetPeerCount\n        internetPeerCount = count\n        if (rideStarted && count > previousCount) publishCachedLocalLocationIfDue(force = true)\n        runOnUiThread { updateTransportStatus() }\n    }\n'''
if new_peer_count not in s:
    s = replace_once(s, old_peer_count, new_peer_count, 'new-rider location republish')

# Re-publish after signaling recovery as well, so a network handover does not leave
# peers displaying only an old/stale marker.
old_state = '''    override fun onInternetState(connected: Boolean, message: String) {\n        runOnUiThread {\n            log(message)\n            internetConnectedSinceMs = if (connected) System.currentTimeMillis() else 0L\n            updateTransportStatus()\n            updateCapturePolicy()\n        }\n    }\n'''
new_state = '''    override fun onInternetState(connected: Boolean, message: String) {\n        if (connected && rideStarted) publishCachedLocalLocationIfDue(force = true)\n        runOnUiThread {\n            log(message)\n            internetConnectedSinceMs = if (connected) System.currentTimeMillis() else 0L\n            updateTransportStatus()\n            updateCapturePolicy()\n        }\n    }\n'''
if new_state not in s:
    s = replace_once(s, old_state, new_state, 'reconnect location republish')

# Rider-friendly header now makes it obvious whether all connected riders have sent
# a live position, without exposing transport/protocol details.
old_share = '''        liveMapShareStatus?.text = if (rideStarted && hasLocationPermission()) {\n            "Location shared with $total rider${if (total == 1) "" else "s"} • Active ride only"\n        } else if (rideStarted) {\n'''
new_share = '''        liveMapShareStatus?.text = if (rideStarted && hasLocationPermission()) {\n            val positionsLive = riderLocations.size + if (myLiveLocation != null) 1 else 0\n            "Location shared with $total rider${if (total == 1) "" else "s"} • $positionsLive position${if (positionsLive == 1) "" else "s"} live"\n        } else if (rideStarted) {\n'''
if new_share not in s:
    s = replace_once(s, old_share, new_share, 'map live position count')

# Add cached publish + resource-only shutdown helpers immediately before map header.
if 'private fun publishCachedLocalLocationIfDue(' not in s:
    anchor = '    private fun updateLiveMapHeader() {\n'
    helper = '''    private fun publishCachedLocalLocationIfDue(force: Boolean) {\n        if (!rideStarted || !hasLocationPermission()) return\n        val snapshot = myLiveLocation ?: return\n        val now = System.currentTimeMillis()\n        if (!force && now - lastLocationPublishMs < LOCATION_STATIONARY_HEARTBEAT_MS) return\n        val phone = prefs.getString(RIDER_PHONE_KEY, "").orEmpty()\n        if (internetNode.publishRiderLocation(\n                snapshot.latitude,\n                snapshot.longitude,\n                snapshot.speedKmh,\n                snapshot.heading,\n                phone,\n            )\n        ) {\n            lastLocationPublishMs = now\n        }\n    }\n\n    private fun shutdownRideRuntimeFromTaskRemoval() {\n        if (!rideStarted) {\n            RideShutdownCoordinator.clear()\n            return\n        }\n        mainHandler.removeCallbacks(stopLobbyScan)\n        mainHandler.removeCallbacks(rideWatchdog)\n        mainHandler.removeCallbacks(locationShareHeartbeat)\n        runCatching { stopLobbyDiscovery() }\n        runCatching { audioEngine.stopTransmit() }\n        runCatching { endLiveMapSession() }\n        runCatching { internetNode.stop() }\n        meshRunning = false\n        runCatching { meshNode.stop() }\n        rideStarted = false\n        directPeerCount = 0\n        internetPeerCount = 0\n        internetConnectedSinceMs = 0L\n        RideShutdownCoordinator.clear()\n        runCatching { audioEngine.release() }\n    }\n\n'''
    s = replace_once(s, anchor, helper + anchor, 'cached location + task shutdown helpers')

# Defensive cleanup if startup itself fails after the coordinator was registered.
if 'RideShutdownCoordinator.clear()\n        runCatching { stopService' not in s:
    anchor = '''        runCatching { meshNode.stop() }\n        runCatching { stopService(Intent(this, RideService::class.java)) }\n'''
    replacement = '''        runCatching { meshNode.stop() }\n        RideShutdownCoordinator.clear()\n        runCatching { stopService(Intent(this, RideService::class.java)) }\n'''
    if anchor in s:
        s = s.replace(anchor, replacement, 1)

# Add vc20 map-heartbeat constants next to the existing map constants.
if 'LOCATION_STATIONARY_HEARTBEAT_MS' not in s:
    anchor = '        private const val MAP_RENDER_MIN_INTERVAL_MS = 500L\n'
    constants = '''        private const val LOCATION_STATIONARY_HEARTBEAT_MS = 5_000L\n        private const val LOCATION_SHARE_HEARTBEAT_CHECK_MS = 1_000L\n'''
    if anchor in s:
        s = s.replace(anchor, anchor + constants, 1)
    else:
        # Fallback if compile-normalization places map constants elsewhere.
        anchor = '    companion object {\n'
        s = replace_once(s, anchor, anchor + constants, 'vc20 heartbeat constants fallback')

p.write_text(s)
