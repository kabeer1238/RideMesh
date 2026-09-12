from pathlib import Path
import re

ROOT = Path('.')

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    return text.replace(old, new, 1)

# -----------------------------------------------------------------------------
# Version
# -----------------------------------------------------------------------------
p = ROOT / 'app/build.gradle.kts'
s = p.read_text()
s = replace_once(
    s,
    'versionCode = 4\n        versionName = "1.0.0-beta3.1-mesh"',
    'versionCode = 5\n        versionName = "1.0.0-beta3.2-offline"',
    'version',
)
p.write_text(s)

# -----------------------------------------------------------------------------
# MeshNode: robust offline discovery, diagnostics and gentle retry.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/mesh/MeshNode.kt'
s = p.read_text()
s = replace_once(s, 'import java.util.concurrent.atomic.AtomicInteger\n', 'import java.util.concurrent.atomic.AtomicBoolean\nimport java.util.concurrent.atomic.AtomicInteger\n', 'AtomicBoolean import')

s = replace_once(
    s,
    '''    data class Diagnostics(\n        val directPeers: Int,\n        val receivedPackets: Int,\n        val relayedPackets: Int,\n        val maxObservedHops: Int,\n        val profile: String,\n    )\n''',
    '''    data class Diagnostics(\n        val directPeers: Int,\n        val receivedPackets: Int,\n        val relayedPackets: Int,\n        val maxObservedHops: Int,\n        val advertisingActive: Boolean,\n        val discoveryActive: Boolean,\n        val discoveredEndpoints: Int,\n        val connectionAttempts: Int,\n        val successfulConnections: Int,\n        val failedConnections: Int,\n        val pendingRequests: Int,\n        val sendFailures: Int,\n        val lastError: String,\n        val profile: String,\n    )\n''',
    'Diagnostics',
)

s = replace_once(
    s,
    '''    private val maxObservedHops = AtomicInteger(0)\n    private val connected = ConcurrentHashMap.newKeySet<String>()\n''',
    '''    private val maxObservedHops = AtomicInteger(0)\n    private val discoveredEndpoints = AtomicInteger(0)\n    private val connectionAttempts = AtomicInteger(0)\n    private val successfulConnections = AtomicInteger(0)\n    private val failedConnections = AtomicInteger(0)\n    private val sendFailures = AtomicInteger(0)\n    private val refreshScheduled = AtomicBoolean(false)\n    private val connected = ConcurrentHashMap.newKeySet<String>()\n''',
    'diagnostic counters',
)

s = replace_once(
    s,
    '''    private var offlinePreferred = false\n    @Volatile private var running = false\n''',
    '''    private var offlinePreferred = false\n    @Volatile private var running = false\n    @Volatile private var advertisingActive = false\n    @Volatile private var discoveryActive = false\n    @Volatile private var lastError = ""\n''',
    'state fields',
)

# Connection result + disconnect recovery.
pattern = re.compile(r'''        override fun onConnectionResult\(endpointId: String, resolution: ConnectionResolution\) \{.*?        override fun onDisconnected\(endpointId: String\) \{.*?        \}\n    \}\n''', re.S)
replacement = '''        override fun onConnectionResult(endpointId: String, resolution: ConnectionResolution) {\n            requested.remove(endpointId)\n            if (resolution.status.isSuccess) {\n                connected.add(endpointId)\n                successfulConnections.incrementAndGet()\n                lastError = ""\n                listener.onLog("Connected: ${displayName(endpointNames[endpointId] ?: endpointId)}")\n            } else {\n                failedConnections.incrementAndGet()\n                lastError = "Connection failed: status ${resolution.status.statusCode}"\n                listener.onLog(lastError)\n                scheduleDiscoveryRefresh("connection failed")\n            }\n            listener.onDirectPeerCount(connected.size)\n        }\n\n        override fun onDisconnected(endpointId: String) {\n            connected.remove(endpointId)\n            requested.remove(endpointId)\n            originEndpoints.entries.removeIf { it.value == endpointId }\n            listener.onLog("Peer disconnected: ${displayName(endpointNames[endpointId] ?: endpointId)}")\n            listener.onDirectPeerCount(connected.size)\n            if (running) scheduleDiscoveryRefresh("peer disconnected")\n        }\n    }\n'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('connection lifecycle block not found')

# Discovery callback with staggered/deterministic handshake.
pattern = re.compile(r'''    private val discoveryCallback = object : EndpointDiscoveryCallback\(\) \{.*?    \}\n\n    fun start\(''', re.S)
replacement = '''    private val discoveryCallback = object : EndpointDiscoveryCallback() {\n        override fun onEndpointFound(endpointId: String, info: DiscoveredEndpointInfo) {\n            val firstSeen = endpointNames.put(endpointId, info.endpointName) == null\n            if (firstSeen) discoveredEndpoints.incrementAndGet()\n            if (!running || parseRideCode(info.endpointName) != rideCode) return\n            if (!isAllowedPeer(parseLabRole(info.endpointName))) return\n            if (connected.contains(endpointId) || requested.contains(endpointId)) return\n\n            if (shouldInitiate(info.endpointName)) {\n                requestPeer(endpointId, info.endpointName, delayed = false)\n            } else {\n                listener.onLog("Found ${displayName(info.endpointName)} • waiting for peer handshake")\n                Thread({\n                    try { Thread.sleep(PASSIVE_CONNECT_DELAY_MS) } catch (_: InterruptedException) { return@Thread }\n                    if (running && !connected.contains(endpointId) && !requested.contains(endpointId)) {\n                        requestPeer(endpointId, info.endpointName, delayed = true)\n                    }\n                }, "RideMesh-PassiveConnect").apply { isDaemon = true; start() }\n            }\n        }\n\n        override fun onEndpointLost(endpointId: String) {\n            requested.remove(endpointId)\n        }\n    }\n\n    private fun requestPeer(endpointId: String, endpointName: String, delayed: Boolean) {\n        if (!running || connected.contains(endpointId) || !requested.add(endpointId)) return\n        connectionAttempts.incrementAndGet()\n        listener.onLog("Found ${displayName(endpointName)} — ${if (delayed) "retrying handshake" else "connecting"}")\n        try {\n            client.requestConnection(\n                advertisedName(),\n                endpointId,\n                lifecycleCallback,\n                ConnectionOptions.Builder()\n                    .setConnectionType(connectionType())\n                    .build(),\n            ).addOnFailureListener { error ->\n                requested.remove(endpointId)\n                failedConnections.incrementAndGet()\n                lastError = "Connection request: ${error.javaClass.simpleName}: ${error.message ?: "error"}"\n                listener.onLog(lastError)\n                scheduleDiscoveryRefresh("request failed")\n            }\n        } catch (t: Throwable) {\n            requested.remove(endpointId)\n            failedConnections.incrementAndGet()\n            lastError = "Connection request: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"\n            listener.onLog(lastError)\n            scheduleDiscoveryRefresh("request exception")\n        }\n    }\n\n    fun start('''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('discovery callback block not found')

# Replace start implementation's counter/start section through before stop().
pattern = re.compile(r'''        receivedPackets\.set\(0\).*?    fun stop\(\) \{''', re.S)
replacement = '''        receivedPackets.set(0)\n        relayedPackets.set(0)\n        maxObservedHops.set(0)\n        discoveredEndpoints.set(0)\n        connectionAttempts.set(0)\n        successfulConnections.set(0)\n        failedConnections.set(0)\n        sendFailures.set(0)\n        advertisingActive = false\n        discoveryActive = false\n        lastError = ""\n        running = true\n        listener.onLog("Starting local mesh for ride ${this.rideCode} • ${if (preferOffline) "OFFLINE BALANCED" else "HYBRID"}")\n        startNearbyEndpoints()\n    }\n\n    private fun startNearbyEndpoints() {\n        if (!running) return\n        val advertising = AdvertisingOptions.Builder()\n            .setStrategy(STRATEGY)\n            .setConnectionType(connectionType())\n            .build()\n        val discovery = DiscoveryOptions.Builder()\n            .setStrategy(STRATEGY)\n            .build()\n\n        try {\n            client.startAdvertising(advertisedName(), SERVICE_ID, lifecycleCallback, advertising)\n                .addOnSuccessListener {\n                    advertisingActive = true\n                    listener.onLog("Local mesh advertising ACTIVE • ${this.riderName}")\n                }\n                .addOnFailureListener { error ->\n                    advertisingActive = false\n                    lastError = "Advertising: ${error.javaClass.simpleName}: ${error.message ?: "unknown"}"\n                    listener.onLog(lastError)\n                    scheduleDiscoveryRefresh("advertising failed")\n                }\n\n            client.startDiscovery(SERVICE_ID, discoveryCallback, discovery)\n                .addOnSuccessListener {\n                    discoveryActive = true\n                    listener.onLog("Local mesh discovery ACTIVE")\n                }\n                .addOnFailureListener { error ->\n                    discoveryActive = false\n                    lastError = "Discovery: ${error.javaClass.simpleName}: ${error.message ?: "unknown"}"\n                    listener.onLog(lastError)\n                    scheduleDiscoveryRefresh("discovery failed")\n                }\n        } catch (t: Throwable) {\n            advertisingActive = false\n            discoveryActive = false\n            lastError = "Nearby start: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"\n            listener.onLog(lastError)\n            scheduleDiscoveryRefresh("start exception")\n        }\n    }\n\n    fun refreshDiscovery(reason: String) {\n        if (!running) return\n        listener.onLog("Refreshing Nearby advertising/discovery • $reason")\n        scheduleDiscoveryRefresh(reason, delayMs = 0L)\n    }\n\n    private fun scheduleDiscoveryRefresh(reason: String, delayMs: Long = NEARBY_RETRY_DELAY_MS) {\n        if (!running || !refreshScheduled.compareAndSet(false, true)) return\n        Thread({\n            try {\n                if (delayMs > 0L) Thread.sleep(delayMs)\n                if (!running) return@Thread\n                runCatching { client.stopAdvertising() }\n                runCatching { client.stopDiscovery() }\n                advertisingActive = false\n                discoveryActive = false\n                Thread.sleep(NEARBY_REFRESH_SETTLE_MS)\n                if (running) {\n                    listener.onLog("Nearby retry • $reason")\n                    startNearbyEndpoints()\n                }\n            } catch (_: InterruptedException) {\n                // App/ride stopped.\n            } finally {\n                refreshScheduled.set(false)\n            }\n        }, "RideMesh-NearbyRetry").apply { isDaemon = true; start() }\n    }\n\n    fun stop() {'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('start block not found')

s = replace_once(
    s,
    '''    fun stop() {\n        running = false\n        runCatching { client.stopAdvertising() }\n        runCatching { client.stopDiscovery() }\n''',
    '''    fun stop() {\n        running = false\n        advertisingActive = false\n        discoveryActive = false\n        runCatching { client.stopAdvertising() }\n        runCatching { client.stopDiscovery() }\n''',
    'stop flags',
)

pattern = re.compile(r'''    fun diagnostics\(\): Diagnostics = Diagnostics\(.*?    \)\n''', re.S)
replacement = '''    fun diagnostics(): Diagnostics = Diagnostics(\n        directPeers = connected.size,\n        receivedPackets = receivedPackets.get(),\n        relayedPackets = relayedPackets.get(),\n        maxObservedHops = maxObservedHops.get(),\n        advertisingActive = advertisingActive,\n        discoveryActive = discoveryActive,\n        discoveredEndpoints = discoveredEndpoints.get(),\n        connectionAttempts = connectionAttempts.get(),\n        successfulConnections = successfulConnections.get(),\n        failedConnections = failedConnections.get(),\n        pendingRequests = requested.size,\n        sendFailures = sendFailures.get(),\n        lastError = lastError,\n        profile = if (offlinePreferred) "OFFLINE BALANCED" else "HYBRID NON-DISRUPTIVE",\n    )\n'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('diagnostics function not found')

s = replace_once(
    s,
    '''                    .addOnFailureListener {\n                        listener.onLog("Send error: ${it.javaClass.simpleName}: ${it.message ?: "unknown"}")\n                    }\n''',
    '''                    .addOnFailureListener {\n                        sendFailures.incrementAndGet()\n                        lastError = "Send: ${it.javaClass.simpleName}: ${it.message ?: "unknown"}"\n                        listener.onLog(lastError)\n                    }\n''',
    'send failure async',
)
s = replace_once(
    s,
    '''            } catch (t: Throwable) {\n                listener.onLog("Send error: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")\n            }\n''',
    '''            } catch (t: Throwable) {\n                sendFailures.incrementAndGet()\n                lastError = "Send: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"\n                listener.onLog(lastError)\n            }\n''',
    'send failure catch',
)

s = replace_once(
    s,
    '''    private fun sanitizeEndpointPart(value: String): String = value.trim().replace('|', '/')\n\n    private fun parseLabRole(endpointName: String): LabRole {\n''',
    '''    private fun sanitizeEndpointPart(value: String): String = value.trim().replace('|', '/')\n\n    private fun parseNodeShort(endpointName: String): String {\n        val parts = endpointName.split('|')\n        return if (parts.size >= 4) parts[3].trim().lowercase() else ""\n    }\n\n    private fun shouldInitiate(endpointName: String): Boolean {\n        val remote = parseNodeShort(endpointName)\n        val local = nodeId.toString().take(8).lowercase()\n        return remote.isBlank() || local <= remote\n    }\n\n    private fun parseLabRole(endpointName: String): LabRole {\n''',
    'node ordering helper',
)

s = replace_once(
    s,
    '''        private const val MAX_TTL = 4\n''',
    '''        private const val MAX_TTL = 4\n        private const val PASSIVE_CONNECT_DELAY_MS = 900L\n        private const val NEARBY_RETRY_DELAY_MS = 1_500L\n        private const val NEARBY_REFRESH_SETTLE_MS = 650L\n''',
    'mesh constants',
)
p.write_text(s)

# -----------------------------------------------------------------------------
# MainActivity: keep offline mesh alive, gentle discovery refresh + diagnostics.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

s = replace_once(
    s,
    '''    private fun ensureLocalMeshRunning(reason: String) {\n        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || meshRunning || !radiosReady()) return\n        meshNode.start(\n''',
    '''    private fun ensureLocalMeshRunning(reason: String) {\n        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || meshRunning) return\n        if (!radiosReady()) {\n            log("LOCAL MESH BLOCKED • ${localRadioSummary()}")\n            return\n        }\n        meshNode.start(\n''',
    'ensure local mesh guard',
)

pattern = re.compile(r'''    private fun restartLocalMesh\(\) \{.*?    \}\n\n    private fun restartLocalMeshForRoleOrMode\(reason: String\) \{.*?    \}\n''', re.S)
replacement = '''    private fun restartLocalMesh() {\n        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || !radiosReady()) return\n        if (transportMode == TransportMode.AUTO && internetNode.isConnected()) return\n        if (meshRunning) {\n            meshNode.refreshDiscovery("automatic reconnect")\n            lastMeshRefreshMs = System.currentTimeMillis()\n            log("Refreshing local advertising/discovery without dropping endpoints")\n        } else {\n            ensureLocalMeshRunning("automatic reconnect")\n        }\n    }\n\n    private fun restartLocalMeshForRoleOrMode(reason: String) {\n        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY) return\n        if (meshRunning) {\n            meshRunning = false\n            meshNode.stop()\n            directPeerCount = 0\n            mainHandler.postDelayed({\n                if (rideStarted && transportMode != TransportMode.INTERNET_ONLY) {\n                    ensureLocalMeshRunning(reason)\n                    updateTransportStatus()\n                    updateCapturePolicy()\n                }\n            }, LOCAL_MESH_RESTART_SETTLE_MS)\n        } else {\n            ensureLocalMeshRunning(reason)\n        }\n    }\n'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('restart mesh functions not found')

s = replace_once(
    s,
    '''                binding.meshStatus.text = if (directPeerCount > 0) {\n                    "OFFLINE LOCAL VOICE • ROLE ${meshLabRole.name}"\n                } else {\n                    "OFFLINE SEARCH • WIFI + BLUETOOTH • ROLE ${meshLabRole.name}"\n                }\n''',
    '''                val diag = meshNode.diagnostics()\n                binding.meshStatus.text = if (directPeerCount > 0) {\n                    "OFFLINE LOCAL VOICE • ROLE ${meshLabRole.name}"\n                } else if (diag.advertisingActive && diag.discoveryActive) {\n                    "OFFLINE SEARCH ACTIVE • ROLE ${meshLabRole.name} • TAP STATUS"\n                } else {\n                    "OFFLINE LINK NEEDS ATTENTION • TAP STATUS"\n                }\n''',
    'local status diagnostics',
)

# Replace radio helper with richer summary but preserve strict Wi-Fi + BT requirement.
s = replace_once(
    s,
    '''    private fun radiosReady(): Boolean {\n        val bluetoothOn = try {\n            getSystemService(BluetoothManager::class.java).adapter?.isEnabled == true\n        } catch (_: Throwable) {\n            false\n        }\n\n        val wifiOn = try {\n            applicationContext.getSystemService(WifiManager::class.java).isWifiEnabled\n        } catch (_: Throwable) {\n            false\n        }\n\n        return bluetoothOn && wifiOn\n    }\n''',
    '''    private fun bluetoothReady(): Boolean = try {\n        getSystemService(BluetoothManager::class.java).adapter?.isEnabled == true\n    } catch (_: Throwable) {\n        false\n    }\n\n    private fun wifiReady(): Boolean = try {\n        applicationContext.getSystemService(WifiManager::class.java).isWifiEnabled\n    } catch (_: Throwable) {\n        false\n    }\n\n    private fun radiosReady(): Boolean = bluetoothReady() && wifiReady()\n\n    private fun localRadioSummary(): String {\n        val missing = requiredPermissions().filter {\n            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED\n        }.map { it.substringAfterLast('.') }\n        return "Wi-Fi ${if (wifiReady()) "ON" else "OFF"} • Bluetooth ${if (bluetoothReady()) "ON" else "OFF"} • Permissions ${if (missing.isEmpty()) "OK" else "MISSING ${missing.joinToString()}"}"\n    }\n''',
    'radio helper',
)

# Insert diagnostics dialog before ride status dialog.
anchor = '    private fun showRideStatusDialog() {\n'
if 'private fun showOfflineDiagnosticsDialog()' not in s:
    diag_fun = '''    private fun showOfflineDiagnosticsDialog() {\n        val diag = meshNode.diagnostics()\n        val message = buildString {\n            append("${localRadioSummary()}\\n\\n")\n            append("Mesh running: ${if (meshRunning) "YES" else "NO"}\\n")\n            append("Profile: ${diag.profile}\\n")\n            append("Advertising: ${if (diag.advertisingActive) "ACTIVE" else "NOT ACTIVE"}\\n")\n            append("Discovery: ${if (diag.discoveryActive) "ACTIVE" else "NOT ACTIVE"}\\n")\n            append("Endpoints discovered: ${diag.discoveredEndpoints}\\n")\n            append("Connection attempts: ${diag.connectionAttempts}\\n")\n            append("Successful connections: ${diag.successfulConnections}\\n")\n            append("Failed connections: ${diag.failedConnections}\\n")\n            append("Pending handshakes: ${diag.pendingRequests}\\n")\n            append("Direct peers: ${diag.directPeers}\\n")\n            append("Packets received: ${diag.receivedPackets}\\n")\n            append("Packets relayed: ${diag.relayedPackets}\\n")\n            append("Max observed hops: ${diag.maxObservedHops}\\n")\n            append("Send failures: ${diag.sendFailures}\\n")\n            append("Last Nearby error: ${diag.lastError.ifBlank { "none" }}\\n\\n")\n            append("For offline testing use the SAME ride code on every phone, Wi-Fi + Bluetooth ON, and LOCAL MESH ONLY. Internet/mobile data may be OFF.")\n        }\n\n        AlertDialog.Builder(this)\n            .setTitle("Offline mesh diagnostics • role ${meshLabRole.name}")\n            .setMessage(message)\n            .setPositiveButton("RETRY MESH") { _, _ ->\n                if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY) {\n                    log("Start a LOCAL/AUTO ride before retrying mesh")\n                } else if (!radiosReady()) {\n                    log("Cannot retry mesh • ${localRadioSummary()}")\n                } else if (meshRunning) {\n                    meshNode.refreshDiscovery("manual diagnostic retry")\n                    lastMeshRefreshMs = System.currentTimeMillis()\n                } else {\n                    ensureLocalMeshRunning("manual diagnostic retry")\n                }\n            }\n            .setNeutralButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n'''
    if anchor not in s:
        raise SystemExit('ride status anchor not found')
    s = s.replace(anchor, diag_fun + anchor, 1)

# Enrich ride status diagnostics and open dedicated diagnostic panel.
s = replace_once(
    s,
    '''                    "Mesh profile: ${diag.profile}\\n" +\n                    "Mesh packets received: ${diag.receivedPackets}\\n" +\n''',
    '''                    "Mesh profile: ${diag.profile}\\n" +\n                    "Advertising: ${if (diag.advertisingActive) "ACTIVE" else "OFF"} • Discovery: ${if (diag.discoveryActive) "ACTIVE" else "OFF"}\\n" +\n                    "Endpoints found: ${diag.discoveredEndpoints} • Attempts: ${diag.connectionAttempts} • Failures: ${diag.failedConnections}\\n" +\n                    "Last mesh error: ${diag.lastError.ifBlank { "none" }}\\n" +\n                    "Mesh packets received: ${diag.receivedPackets}\\n" +\n''',
    'ride status diag fields',
)
s = replace_once(
    s,
    '''            .setPositiveButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }\n            .setNeutralButton("TRANSPORT") { _, _ -> showTransportModeDialog() }\n''',
    '''            .setPositiveButton("OFFLINE DIAG") { _, _ -> showOfflineDiagnosticsDialog() }\n            .setNeutralButton("TRANSPORT") { _, _ -> showTransportModeDialog() }\n''',
    'ride status buttons',
)

s = replace_once(
    s,
    '''                    "LOCAL MESH ONLY keeps Internet voice off and prevents mesh sleeping for offline testing. Wi-Fi + Bluetooth should be ON; Internet may be OFF.\\n\\n" +\n''',
    '''                    "LOCAL MESH ONLY keeps Internet voice off and prevents mesh sleeping for offline testing. Wi-Fi + Bluetooth should be ON; Internet may be OFF. Use RIDE STATUS → OFFLINE DIAG to see advertising, discovery, handshake and relay state.\\n\\n" +\n''',
    'settings diagnostic help',
)

# Include transport diagnostics in bug report.
s = replace_once(
    s,
    '''            append("Current path: ${if (rideStarted) binding.networkTile.text else "Not riding"}\\n")\n            append("Problem: ")\n''',
    '''            append("Current path: ${if (rideStarted) binding.networkTile.text else "Not riding"}\\n")\n            append("Transport mode: ${transportModeLabel()} • role ${meshLabRole.name}\\n")\n            if (::meshNode.isInitialized) {\n                val d = meshNode.diagnostics()\n                append("Mesh: adv=${d.advertisingActive}, disc=${d.discoveryActive}, found=${d.discoveredEndpoints}, attempts=${d.connectionAttempts}, success=${d.successfulConnections}, failures=${d.failedConnections}, peers=${d.directPeers}, relayed=${d.relayedPackets}, hops=${d.maxObservedHops}, error=${d.lastError.ifBlank { "none" }}\\n")\n            }\n            append("Problem: ")\n''',
    'bug report diagnostics',
)

s = replace_once(s, 'private const val LOCAL_MESH_REFRESH_MS = 25_000L', 'private const val LOCAL_MESH_REFRESH_MS = 8_000L', 'refresh interval')
s = replace_once(
    s,
    'private const val LOCAL_MESH_REFRESH_MS = 8_000L\n',
    'private const val LOCAL_MESH_REFRESH_MS = 8_000L\n        private const val LOCAL_MESH_RESTART_SETTLE_MS = 700L\n',
    'restart settle constant',
)
p.write_text(s)

print('Beta3.2 offline recovery patch applied')
