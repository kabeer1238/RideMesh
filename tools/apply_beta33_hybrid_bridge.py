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
    'versionCode = 5\n        versionName = "1.0.0-beta3.2-offline"',
    'versionCode = 6\n        versionName = "1.0.0-beta3.3-hybridbridge"',
    'version',
)
p.write_text(s)


# -----------------------------------------------------------------------------
# MeshNode: shared identity, deterministic frame IDs, stable fast reconnect.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/mesh/MeshNode.kt'
s = p.read_text()

s = replace_once(
    s,
    '''class MeshNode(\n    context: Context,\n    private val listener: Listener,\n) {''',
    '''class MeshNode(\n    context: Context,\n    private val listener: Listener,\n    private val nodeId: UUID = UUID.randomUUID(),\n) {''',
    'MeshNode constructor',
)
s = replace_once(s, '    private val nodeId = UUID.randomUUID()\n', '', 'remove MeshNode random id')

s = replace_once(
    s,
    '''    data class RiderPeer(\n        val endpointId: String,\n        val riderName: String,\n        val deviceName: String,\n        val qualityBars: Int = 4,\n    ) {''',
    '''    data class RiderPeer(\n        val endpointId: String,\n        val sourceId: String,\n        val riderName: String,\n        val deviceName: String,\n        val qualityBars: Int = 4,\n    ) {''',
    'Mesh rider source identity',
)

# Avoid tearing down all Nearby discovery for a single handshake failure.
s = replace_once(
    s,
    '''                lastError = "Connection failed: status ${resolution.status.statusCode}"\n                listener.onLog(lastError)\n                scheduleDiscoveryRefresh("connection failed")''',
    '''                lastError = "Connection failed: status ${resolution.status.statusCode}"\n                listener.onLog(lastError)\n                endpointNames[endpointId]?.let { schedulePeerRetry(endpointId, it, "connection failed") }''',
    'connection result retry',
)
s = replace_once(
    s,
    '''            listener.onLog("Peer disconnected: ${displayName(endpointNames[endpointId] ?: endpointId)}")\n            listener.onDirectPeerCount(connected.size)\n            if (running) scheduleDiscoveryRefresh("peer disconnected")''',
    '''            listener.onLog("Peer disconnected: ${displayName(endpointNames[endpointId] ?: endpointId)}")\n            listener.onDirectPeerCount(connected.size)\n            if (running) endpointNames[endpointId]?.let { schedulePeerRetry(endpointId, it, "peer disconnected") }''',
    'disconnect retry',
)
s = replace_once(
    s,
    '''                lastError = "Connection request: ${error.javaClass.simpleName}: ${error.message ?: "error"}"\n                listener.onLog(lastError)\n                scheduleDiscoveryRefresh("request failed")''',
    '''                lastError = "Connection request: ${error.javaClass.simpleName}: ${error.message ?: "error"}"\n                listener.onLog(lastError)\n                schedulePeerRetry(endpointId, endpointName, "request failed")''',
    'request async retry',
)
s = replace_once(
    s,
    '''            lastError = "Connection request: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"\n            listener.onLog(lastError)\n            scheduleDiscoveryRefresh("request exception")''',
    '''            lastError = "Connection request: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}"\n            listener.onLog(lastError)\n            schedulePeerRetry(endpointId, endpointName, "request exception")''',
    'request exception retry',
)

s = replace_once(
    s,
    '''    fun start(\n        riderName: String,''',
    '''    private fun schedulePeerRetry(endpointId: String, endpointName: String, reason: String) {\n        Thread({\n            try { Thread.sleep(PEER_RETRY_DELAY_MS) } catch (_: InterruptedException) { return@Thread }\n            if (running && !connected.contains(endpointId) && !requested.contains(endpointId)) {\n                listener.onLog("Retrying ${displayName(endpointName)} • $reason")\n                requestPeer(endpointId, endpointName, delayed = true)\n            }\n        }, "RideMesh-PeerRetry").apply { isDaemon = true; start() }\n    }\n\n    fun start(\n        riderName: String,''',
    'peer retry helper',
)

# Expose full shared source identity in peer metadata.
s = replace_once(
    s,
    '''        RiderPeer(\n            endpointId = endpointId,\n            riderName = parseRiderName(endpointName),\n            deviceName = parseDeviceName(endpointName),\n        )''',
    '''        RiderPeer(\n            endpointId = endpointId,\n            sourceId = parseNodeId(endpointName)?.toString() ?: endpointId,\n            riderName = parseRiderName(endpointName),\n            deviceName = parseDeviceName(endpointName),\n        )''',
    'direct peer source id',
)

# Replace local frame creation with a shared-origin API. Deterministic packet IDs
# ensure re-entry from another bridge is discarded by the local mesh itself.
pattern = re.compile(r'''    fun sendLocalAudio\(audio: ByteArray\) \{.*?    \}\n\n    private fun relay''', re.S)
replacement = '''    fun sendLocalAudio(audio: ByteArray) {\n        sendAudioFrame(\n            origin = nodeId,\n            frameSequence = sequence.incrementAndGet(),\n            timestampMs = System.currentTimeMillis(),\n            audio = audio,\n        )\n    }\n\n    fun sendAudioFrame(origin: UUID, frameSequence: Int, timestampMs: Long, audio: ByteArray) {\n        if (!running || audio.isEmpty() || connected.isEmpty()) return\n        val packet = MeshPacket(\n            ttl = MAX_TTL,\n            origin = origin,\n            packetId = deterministicPacketId(origin, frameSequence, timestampMs),\n            sequence = frameSequence,\n            timestampMs = timestampMs,\n            audio = audio,\n        )\n        synchronized(seenPackets) {\n            if (seenPackets.containsKey(packet.packetId)) return\n            seenPackets[packet.packetId] = true\n        }\n        relay(packet, excludeEndpoint = null)\n    }\n\n    private fun deterministicPacketId(origin: UUID, frameSequence: Int, timestampMs: Long): UUID =\n        UUID.nameUUIDFromBytes("$origin:$frameSequence:$timestampMs".toByteArray(Charsets.UTF_8))\n\n    private fun relay'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('Mesh sendAudioFrame block not found')

s = replace_once(
    s,
    '''    private fun advertisedName(): String =\n        "$rideCode|$riderName|${labRole.name}|${nodeId.toString().take(8)}|$deviceName"''',
    '''    private fun advertisedName(): String =\n        "$rideCode|$riderName|${labRole.name}|$nodeId|$deviceName"''',
    'full advertised node id',
)

s = replace_once(
    s,
    '''    private fun parseNodeShort(endpointName: String): String {\n        val parts = endpointName.split('|')\n        return if (parts.size >= 4) parts[3].trim().lowercase() else ""\n    }\n\n    private fun shouldInitiate(endpointName: String): Boolean {''',
    '''    private fun parseNodeShort(endpointName: String): String {\n        val parts = endpointName.split('|')\n        return if (parts.size >= 4) parts[3].trim().lowercase() else ""\n    }\n\n    private fun parseNodeId(endpointName: String): UUID? {\n        val parts = endpointName.split('|')\n        return if (parts.size >= 4) runCatching { UUID.fromString(parts[3].trim()) }.getOrNull() else null\n    }\n\n    private fun shouldInitiate(endpointName: String): Boolean {''',
    'parse full node id',
)

s = replace_once(
    s,
    '''        private const val PASSIVE_CONNECT_DELAY_MS = 900L\n        private const val NEARBY_RETRY_DELAY_MS = 1_500L\n        private const val NEARBY_REFRESH_SETTLE_MS = 650L''',
    '''        private const val PASSIVE_CONNECT_DELAY_MS = 250L\n        private const val PEER_RETRY_DELAY_MS = 700L\n        private const val NEARBY_RETRY_DELAY_MS = 2_500L\n        private const val NEARBY_REFRESH_SETTLE_MS = 350L''',
    'mesh retry timing',
)
p.write_text(s)


# -----------------------------------------------------------------------------
# InternetNode: shared identity + preserved source/sequence bridge publishing.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt'
s = p.read_text()

s = replace_once(s, 'import java.util.UUID\n', 'import java.util.Collections\nimport java.util.LinkedHashMap\nimport java.util.UUID\n', 'Internet LRU imports')
s = replace_once(
    s,
    'class InternetNode(private val listener: Listener) {',
    'class InternetNode(private val listener: Listener, private val nodeId: UUID = UUID.randomUUID()) {',
    'InternetNode constructor',
)
s = replace_once(s, '    private val nodeId = UUID.randomUUID()\n', '', 'remove Internet random id')

s = replace_once(
    s,
    '''    private val reportedPeerCount = AtomicInteger(-1)\n''',
    '''    private val reportedPeerCount = AtomicInteger(-1)\n    private val seenAudioFrames: MutableMap<String, Boolean> = Collections.synchronizedMap(\n        object : LinkedHashMap<String, Boolean>(1024, 0.75f, true) {\n            override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Boolean>?): Boolean = size > 4096\n        }\n    )\n''',
    'Internet seen frame cache',
)

pattern = re.compile(r'''    fun sendLocalAudio\(audio: ByteArray\): Boolean \{.*?    \}\n\n    fun stop\(\)''', re.S)
replacement = '''    fun sendLocalAudio(audio: ByteArray): Boolean = sendAudioFrame(\n        origin = nodeId,\n        frameSequence = sequence.incrementAndGet(),\n        timestampMs = System.currentTimeMillis(),\n        audio = audio,\n    )\n\n    fun sendAudioFrame(origin: UUID, frameSequence: Int, timestampMs: Long, audio: ByteArray): Boolean {\n        if (audio.isEmpty() || !connected.get()) return false\n        rememberFrame(origin, frameSequence)\n        val packet = encode(\n            InternetPacket(\n                origin = origin,\n                sequence = frameSequence,\n                timestampMs = timestampMs,\n                audio = audio,\n            )\n        )\n        return try {\n            sendMqttPublish(audioTopic, packet)\n            true\n        } catch (_: Throwable) {\n            markDisconnected("Internet send failed • local mesh stays active")\n            closeSocket()\n            false\n        }\n    }\n\n    private fun rememberFrame(origin: UUID, frameSequence: Int): Boolean {\n        val key = "$origin:$frameSequence"\n        synchronized(seenAudioFrames) {\n            if (seenAudioFrames.containsKey(key)) return false\n            seenAudioFrames[key] = true\n            return true\n        }\n    }\n\n    fun stop()'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('Internet sendAudioFrame block not found')

s = replace_once(
    s,
    '''                val packet = decode(payload) ?: return\n                if (packet.origin == nodeId) return\n                updateLinkStats(packet)''',
    '''                val packet = decode(payload) ?: return\n                if (packet.origin == nodeId) return\n                if (!rememberFrame(packet.origin, packet.sequence)) return\n                updateLinkStats(packet)''',
    'Internet receive dedupe',
)

s = replace_once(
    s,
    '''        reconnectAttempt = 0\n    }\n''',
    '''        reconnectAttempt = 0\n        synchronized(seenAudioFrames) { seenAudioFrames.clear() }\n    }\n''',
    'Internet stop cache clear',
)
p.write_text(s)


# -----------------------------------------------------------------------------
# MainActivity: simultaneous local+Internet AUTO bridge with cross-path dedupe.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

s = replace_once(
    s,
    'import java.util.Date\nimport java.util.Locale\nimport java.util.concurrent.ConcurrentHashMap\n',
    'import java.util.Collections\nimport java.util.Date\nimport java.util.LinkedHashMap\nimport java.util.Locale\nimport java.util.UUID\nimport java.util.concurrent.ConcurrentHashMap\nimport java.util.concurrent.atomic.AtomicInteger\n',
    'Main hybrid imports',
)

s = replace_once(
    s,
    '''    private val speakingUntilMs = ConcurrentHashMap<String, Long>()\n\n    private var rideStarted = false''',
    '''    private val speakingUntilMs = ConcurrentHashMap<String, Long>()\n    private val hybridNodeId: UUID by lazy {\n        val saved = prefs.getString(HYBRID_NODE_ID_KEY, null)\n        runCatching { UUID.fromString(saved) }.getOrElse {\n            val generated = UUID.randomUUID()\n            prefs.edit().putString(HYBRID_NODE_ID_KEY, generated.toString()).apply()\n            generated\n        }\n    }\n    private val hybridSequence = AtomicInteger(0)\n    private val bridgeLocalToInternet = AtomicInteger(0)\n    private val bridgeInternetToLocal = AtomicInteger(0)\n    private val duplicateFramesDropped = AtomicInteger(0)\n    private val seenHybridFrames: MutableMap<String, Boolean> = Collections.synchronizedMap(\n        object : LinkedHashMap<String, Boolean>(1024, 0.75f, true) {\n            override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, Boolean>?): Boolean = size > 4096\n        }\n    )\n\n    private var rideStarted = false''',
    'Main hybrid state',
)

s = replace_once(
    s,
    '    private enum class TransportMode { AUTO, LOCAL_ONLY, INTERNET_ONLY }\n',
    '    private enum class TransportMode { AUTO, LOCAL_ONLY, INTERNET_ONLY }\n    private enum class IncomingPath { LOCAL, INTERNET }\n',
    'incoming path enum',
)

s = replace_once(
    s,
    '''            log("Nearby invite scan finished")\n            if (!internetNode.isConnected() || !binding.batterySaver.isChecked) {\n                ensureLocalMeshRunning("invite scan finished")\n            }''',
    '''            log("Nearby invite scan finished")\n            if (transportMode != TransportMode.INTERNET_ONLY) {\n                ensureLocalMeshRunning("invite scan finished")\n            }''',
    'stop lobby keeps mesh',
)

# AUTO watchdog: local mesh never sleeps merely because Internet is healthy.
pattern = re.compile(r'''                TransportMode\.AUTO -> \{\n                    if \(internetNode\.isConnected\(\)\) \{.*?                    \}\n                \}\n''', re.S)
replacement = '''                TransportMode.AUTO -> {\n                    ensureLocalMeshRunning("AUTO hybrid bridge")\n                    if (meshRunning && directPeerCount == 0 && now - lastMeshRefreshMs >= LOCAL_MESH_REFRESH_MS) {\n                        val diag = meshNode.diagnostics()\n                        if (!diag.advertisingActive || !diag.discoveryActive || now - lastMeshRefreshMs >= LOCAL_MESH_FORCE_REFRESH_MS) {\n                            restartLocalMesh()\n                        }\n                    }\n                }\n'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('AUTO watchdog block not found')

# During an active ride the mesh transport itself already discovers same-code riders.
# Do not stop it to run a separate lobby scan; use QR for new-code invitations.
pattern = re.compile(r'''    private fun startNearbyLobby\(\) \{.*?        lobbyNode\.start\(\n            binding\.riderName\.text\?\.toString\(\)\.orEmpty\(\),\n            normalizedRideCode\(\),\n        \)\n        binding\.findNearby\.text = "SCANNING…"\n        mainHandler\.postDelayed\(stopLobbyScan, LOBBY_SCAN_WINDOW_MS\)\n        log\(if \(rideStarted\) "Live nearby rider scan started • Internet voice continues" else "Short nearby scan started"\)\n    \}\n''', re.S)
replacement = '''    private fun startNearbyLobby() {\n        if (!radiosReady()) {\n            log("Nearby riders unavailable: turn ON Bluetooth and Wi-Fi, then try again")\n            return\n        }\n\n        if (rideStarted) {\n            AlertDialog.Builder(this)\n                .setTitle("Keep the hybrid voice bridge active")\n                .setMessage("RideMesh is already discovering riders using your active ride code. To add a new rider without interrupting a local/offline link, share the ride QR/code.")\n                .setPositiveButton("SHARE QR") { _, _ -> shareRideQr() }\n                .setNegativeButton("CLOSE", null)\n                .show()\n            return\n        }\n\n        stopLobbyDiscovery()\n        clearNearbyRiders("Scanning nearby…")\n        lobbyNode.start(\n            binding.riderName.text?.toString().orEmpty(),\n            normalizedRideCode(),\n        )\n        binding.findNearby.text = "SCANNING…"\n        mainHandler.postDelayed(stopLobbyScan, LOBBY_SCAN_WINDOW_MS)\n        log("Short nearby scan started")\n    }\n'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('active lobby scan block not found')

s = replace_once(
    s,
    '''        meshNode = MeshNode(applicationContext, this)\n        lobbyNode = LobbyNode(applicationContext, this)\n        internetNode = InternetNode(this)''',
    '''        meshNode = MeshNode(applicationContext, this, hybridNodeId)\n        lobbyNode = LobbyNode(applicationContext, this)\n        internetNode = InternetNode(this, hybridNodeId)''',
    'shared transport identity constructors',
)

s = replace_once(
    s,
    '''            internetConnectedSinceMs = 0L\n            lastMeshRefreshMs = 0L\n\n            applySelectedAudioRoute()''',
    '''            internetConnectedSinceMs = 0L\n            lastMeshRefreshMs = 0L\n            hybridSequence.set(0)\n            bridgeLocalToInternet.set(0)\n            bridgeInternetToLocal.set(0)\n            duplicateFramesDropped.set(0)\n            synchronized(seenHybridFrames) { seenHybridFrames.clear() }\n\n            applySelectedAudioRoute()''',
    'reset bridge stats',
)

pattern = re.compile(r'''    private fun sendHybridAudio\(audio: ByteArray\) \{.*?    \}\n\n    private fun ensureLocalMeshRunning''', re.S)
replacement = '''    private fun sendHybridAudio(audio: ByteArray) {\n        if (!rideStarted || audio.isEmpty()) return\n        val frameSequence = hybridSequence.incrementAndGet()\n        val timestampMs = System.currentTimeMillis()\n\n        when (transportMode) {\n            TransportMode.LOCAL_ONLY -> {\n                ensureLocalMeshRunning("local voice path")\n                meshNode.sendAudioFrame(hybridNodeId, frameSequence, timestampMs, audio)\n            }\n            TransportMode.INTERNET_ONLY -> {\n                if (internetNode.isConnected()) {\n                    internetNode.sendAudioFrame(hybridNodeId, frameSequence, timestampMs, audio)\n                }\n            }\n            TransportMode.AUTO -> {\n                // AUTO is simultaneous hybrid, not Internet-OR-local. A healthy local\n                // peer remains reachable while Internet riders join the same group.\n                ensureLocalMeshRunning("AUTO simultaneous voice")\n                if (directPeerCount > 0) {\n                    meshNode.sendAudioFrame(hybridNodeId, frameSequence, timestampMs, audio)\n                }\n                if (internetNode.isConnected()) {\n                    internetNode.sendAudioFrame(hybridNodeId, frameSequence, timestampMs, audio)\n                }\n            }\n        }\n    }\n\n    private fun ensureLocalMeshRunning'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('sendHybridAudio block not found')

s = replace_once(
    s,
    '''        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || !radiosReady()) return\n        if (transportMode == TransportMode.AUTO && internetNode.isConnected()) return\n        if (meshRunning) {''',
    '''        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || !radiosReady()) return\n        if (meshRunning) {''',
    'restart mesh while internet active',
)

s = replace_once(
    s,
    '''            TransportMode.AUTO -> {\n                if (!binding.batterySaver.isChecked) {\n                    ensureLocalMeshRunning("Max Link selected")\n                } else if (!internetNode.isConnected()) {\n                    ensureLocalMeshRunning("Internet unavailable")\n                }\n            }''',
    '''            TransportMode.AUTO -> {\n                ensureLocalMeshRunning("AUTO hybrid keeps local bridge available")\n            }''',
    'battery policy hybrid keepalive',
)

# Replace separate receive handlers with one cross-path dedupe/bridge router.
pattern = re.compile(r'''    override fun onAudioPacket\(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray\) \{.*?    override fun onInternetState''', re.S)
replacement = '''    override fun onAudioPacket(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {\n        handleIncomingAudio(sourceId, sequence, timestampMs, audio, IncomingPath.LOCAL)\n    }\n\n    private fun rememberHybridFrame(sourceId: String, sequence: Int): Boolean {\n        val key = "$sourceId:$sequence"\n        synchronized(seenHybridFrames) {\n            if (seenHybridFrames.containsKey(key)) {\n                duplicateFramesDropped.incrementAndGet()\n                return false\n            }\n            seenHybridFrames[key] = true\n            return true\n        }\n    }\n\n    private fun handleIncomingAudio(\n        sourceId: String,\n        sequence: Int,\n        timestampMs: Long,\n        audio: ByteArray,\n        path: IncomingPath,\n    ) {\n        if (!rideStarted || audio.isEmpty()) return\n        if (sourceId.equals(hybridNodeId.toString(), ignoreCase = true)) return\n        if (!rememberHybridFrame(sourceId, sequence)) return\n\n        markRiderSpeaking(sourceId)\n        audioEngine.playIncoming(sourceId, sequence, timestampMs, audio)\n\n        if (transportMode != TransportMode.AUTO) return\n        val origin = runCatching { UUID.fromString(sourceId) }.getOrNull() ?: return\n        when (path) {\n            IncomingPath.LOCAL -> {\n                if (internetNode.isConnected() && internetNode.sendAudioFrame(origin, sequence, timestampMs, audio)) {\n                    bridgeLocalToInternet.incrementAndGet()\n                }\n            }\n            IncomingPath.INTERNET -> {\n                ensureLocalMeshRunning("bridge Internet to local")\n                if (meshRunning && directPeerCount > 0) {\n                    meshNode.sendAudioFrame(origin, sequence, timestampMs, audio)\n                    bridgeInternetToLocal.incrementAndGet()\n                }\n            }\n        }\n    }\n\n    override fun onInternetState'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('incoming local handler block not found')

s = replace_once(
    s,
    '''    override fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {\n        if (!rideStarted) return\n        markRiderSpeaking(sourceId)\n        audioEngine.playIncoming(sourceId, sequence, timestampMs, audio)\n    }''',
    '''    override fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {\n        handleIncomingAudio(sourceId, sequence, timestampMs, audio, IncomingPath.INTERNET)\n    }''',
    'incoming internet handler',
)

# AUTO status should show simultaneous path explicitly.
s = replace_once(
    s,
    '''                    internetNode.isConnected() -> {\n                        binding.networkTile.text = "INTERNET"\n                        binding.riderCount.text = "RIDE ACTIVE"\n                        binding.meshStatus.text = if (binding.batterySaver.isChecked && !meshRunning) {\n                            "INTERNET VOICE • AUTO LOCAL FALLBACK"\n                        } else {\n                            "INTERNET VOICE • LOCAL MESH WARM"\n                        }\n                    }''',
    '''                    internetNode.isConnected() && directPeerCount > 0 -> {\n                        binding.networkTile.text = "HYBRID"\n                        binding.riderCount.text = "RIDE ACTIVE"\n                        binding.meshStatus.text = "INTERNET + LOCAL BRIDGE • BOTH PATHS LIVE"\n                    }\n                    internetNode.isConnected() -> {\n                        binding.networkTile.text = "INTERNET"\n                        binding.riderCount.text = "RIDE ACTIVE"\n                        binding.meshStatus.text = "INTERNET VOICE • LOCAL DISCOVERY ACTIVE"\n                    }''',
    'AUTO hybrid status',
)

s = replace_once(
    s,
    '''            TransportMode.AUTO -> when {\n                internetNode.isConnected() -> "Internet Voice\\nActive"\n                directPeerCount > 0 -> "Local Mesh\\nActive"\n                else -> "Internet + Mesh\\nReady"\n            }''',
    '''            TransportMode.AUTO -> when {\n                internetNode.isConnected() && directPeerCount > 0 -> "Hybrid Bridge\\nActive"\n                internetNode.isConnected() -> "Internet + Mesh\\nSearching"\n                directPeerCount > 0 -> "Local Mesh\\nActive"\n                else -> "Internet + Mesh\\nReady"\n            }''',
    'home hybrid status',
)

# Rider count and grid merge Internet and local identities instead of hiding locals when Internet is present.
pattern = re.compile(r'''        val visibleRiderTotal = when \(transportMode\) \{.*?        binding\.activeRiders\.text = "RIDERS \$visibleRiderTotal"''', re.S)
replacement = '''        val visibleRiderTotal = connectedRiderCount()\n        binding.activeRiders.text = "RIDERS $visibleRiderTotal"'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('visible rider count block not found')

s = replace_once(
    s,
    '''    private fun markRiderSpeaking(key: String) {''',
    '''    private fun connectedRiderCount(): Int {\n        val identities = linkedSetOf<String>()\n        if (internetNode.isConnected()) {\n            internetNode.remotePeers().forEach {\n                identities += "${it.displayName}|${it.deviceName}".lowercase(Locale.ROOT)\n            }\n        }\n        if (meshRunning) {\n            meshNode.directPeers().forEach {\n                identities += "${it.displayName}|${it.deviceName}".lowercase(Locale.ROOT)\n            }\n        }\n        return identities.size + 1\n    }\n\n    private fun markRiderSpeaking(key: String) {''',
    'connected rider count helper',
)

pattern = re.compile(r'''        if \(internetNode\.isConnected\(\)\) \{\n            internetNode\.remotePeers\(\)\.forEach \{ peer ->.*?        \}\n\n        val visible = riders\.take''', re.S)
replacement = '''        val riderIdentities = linkedSetOf<String>()\n        if (internetNode.isConnected()) {\n            internetNode.remotePeers().forEach { peer ->\n                val identity = "${peer.displayName}|${peer.deviceName}".lowercase(Locale.ROOT)\n                if (riderIdentities.add(identity)) {\n                    riders += RiderTile(\n                        key = peer.id.toString(),\n                        name = peer.displayName,\n                        device = peer.deviceName,\n                        qualityBars = peer.qualityBars,\n                        path = "Internet",\n                    )\n                }\n            }\n        }\n        if (meshRunning) {\n            meshNode.directPeers().forEach { peer ->\n                val identity = "${peer.displayName}|${peer.deviceName}".lowercase(Locale.ROOT)\n                if (riderIdentities.add(identity)) {\n                    riders += RiderTile(\n                        key = peer.sourceId,\n                        name = peer.displayName,\n                        device = peer.deviceName,\n                        qualityBars = peer.qualityBars,\n                        path = "Local",\n                    )\n                }\n            }\n        }\n\n        val visible = riders.take'''
s, n = pattern.subn(replacement, s, count=1)
if n != 1:
    raise SystemExit('rider grid merge block not found')

s = replace_once(
    s,
    '''            "AUTO HYBRID — Internet first + local fallback",''',
    '''            "AUTO HYBRID — Internet + local mesh simultaneously",''',
    'transport label',
)

s = replace_once(
    s,
    '''            TransportMode.AUTO -> when {\n                internetNode.isConnected() -> "Internet"\n                directPeerCount > 0 -> "Local mesh"\n                else -> "Reconnecting"\n            }''',
    '''            TransportMode.AUTO -> when {\n                internetNode.isConnected() && directPeerCount > 0 -> "Hybrid bridge — Internet + local mesh"\n                internetNode.isConnected() -> "Internet + local discovery"\n                directPeerCount > 0 -> "Local mesh"\n                else -> "Reconnecting"\n            }''',
    'ride status path',
)

s = replace_once(
    s,
    '''                    "Max observed hops: ${diag.maxObservedHops}\\n" +\n                    "Internet riders: ${if (internetNode.isConnected()) internetPeerCount + 1 else 0}\\n" +''',
    '''                    "Max observed hops: ${diag.maxObservedHops}\\n" +\n                    "Bridge local → Internet: ${bridgeLocalToInternet.get()} frames\\n" +\n                    "Bridge Internet → local: ${bridgeInternetToLocal.get()} frames\\n" +\n                    "Cross-path duplicates dropped: ${duplicateFramesDropped.get()}\\n" +\n                    "Internet riders: ${if (internetNode.isConnected()) internetPeerCount + 1 else 0}\\n" +''',
    'bridge diagnostics',
)

s = replace_once(
    s,
    '''        private const val INTERNET_STABLE_BEFORE_MESH_SLEEP_MS = 15_000L\n        private const val LOCAL_MESH_REFRESH_MS = 8_000L\n        private const val LOCAL_MESH_RESTART_SETTLE_MS = 700L''',
    '''        private const val LOCAL_MESH_REFRESH_MS = 12_000L\n        private const val LOCAL_MESH_FORCE_REFRESH_MS = 30_000L\n        private const val LOCAL_MESH_RESTART_SETTLE_MS = 450L''',
    'hybrid mesh timings',
)
s = replace_once(
    s,
    '''        private const val BETA_FIRST_LAUNCH_KEY = "beta_first_launch_ms_v2"''',
    '''        private const val HYBRID_NODE_ID_KEY = "hybrid_node_id_v1"\n        private const val BETA_FIRST_LAUNCH_KEY = "beta_first_launch_ms_v2"''',
    'hybrid id key',
)
p.write_text(s)

print('Beta3.3 hybrid bridge patch applied')
