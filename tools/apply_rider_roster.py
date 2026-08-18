from pathlib import Path


def replace_once(path: str, old: str, new: str, marker: str | None = None) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if marker and marker in text:
        return
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


# Install identity bump so testers can update over the previous UI-refresh APK.
replace_once(
    "app/build.gradle.kts",
    'versionCode = 12\n        versionName = "0.4.2-beta1.1"',
    'versionCode = 13\n        versionName = "0.4.3-beta1.1"',
    marker='versionName = "0.4.3-beta1.1"',
)

# Internet presence: retain the original first 24 bytes for backward compatibility,
# then append rider-name and device-name metadata for the roster.
internet_path = "app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt"
replace_once(
    internet_path,
    'private val peers = ConcurrentHashMap<UUID, Long>()\n    private val reportedPeerCount = AtomicInteger(-1)\n\n    @Volatile private var baseTopic: String = ""',
    'private val peers = ConcurrentHashMap<UUID, RiderPeer>()\n    private val reportedPeerCount = AtomicInteger(-1)\n\n    @Volatile private var riderName: String = "Rider"\n    @Volatile private var deviceName: String = "Android device"\n    @Volatile private var baseTopic: String = ""',
    marker='ConcurrentHashMap<UUID, RiderPeer>()',
)
replace_once(
    internet_path,
    'fun start(rideCode: String) {\n        stop()\n        val safeRide = rideCode.trim().uppercase().ifBlank { "RIDE01" }',
    'fun start(rideCode: String, riderName: String, deviceName: String) {\n        stop()\n        this.riderName = sanitizeIdentity(riderName, "Rider", MAX_RIDER_NAME_BYTES)\n        this.deviceName = sanitizeIdentity(deviceName, "Android device", MAX_DEVICE_NAME_BYTES)\n        val safeRide = rideCode.trim().uppercase().ifBlank { "RIDE01" }',
    marker='fun start(rideCode: String, riderName: String, deviceName: String)',
)
replace_once(
    internet_path,
    'fun remotePeerCount(): Int = peers.size\n\n    fun sendLocalAudio(audio: ByteArray): Boolean {',
    '''fun remotePeerCount(): Int = peers.size

    fun remotePeers(): List<RiderPeer> = peers.values
        .sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName })

    fun sendLocalAudio(audio: ByteArray): Boolean {''',
    marker='fun remotePeers(): List<RiderPeer>',
)
replace_once(
    internet_path,
    'markPeer(packet.origin)\n                listener.onInternetAudio(packet.audio)',
    'touchPeer(packet.origin)\n                listener.onInternetAudio(packet.audio)',
    marker='touchPeer(packet.origin)',
)
replace_once(
    internet_path,
    '''    private fun publishPresence() {
        if (!connected.get()) return
        val payload = ByteBuffer.allocate(PRESENCE_BYTES)
            .order(ByteOrder.BIG_ENDIAN)
            .putLong(nodeId.mostSignificantBits)
            .putLong(nodeId.leastSignificantBits)
            .putLong(System.currentTimeMillis())
            .array()
        sendMqttPublish(presenceTopic, payload)
    }

    private fun handlePresence(payload: ByteArray) {
        if (payload.size < PRESENCE_BYTES) return
        try {
            val buffer = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)
            val origin = UUID(buffer.long, buffer.long)
            buffer.long // sender timestamp; local receive time is used for expiry
            if (origin == nodeId) return
            markPeer(origin)
        } catch (_: Throwable) {
        }
    }

    private fun markPeer(id: UUID) {
        peers[id] = System.currentTimeMillis()
        notifyPeerCount()
    }

    private fun prunePeers(now: Long) {
        peers.entries.removeIf { now - it.value > PRESENCE_TIMEOUT_MS }
        notifyPeerCount()
    }
''',
    '''    private fun publishPresence() {
        if (!connected.get()) return
        sendMqttPublish(
            presenceTopic,
            encodePresence(
                PresencePacket(
                    origin = nodeId,
                    timestampMs = System.currentTimeMillis(),
                    riderName = riderName,
                    deviceName = deviceName,
                )
            )
        )
    }

    private fun handlePresence(payload: ByteArray) {
        val presence = decodePresence(payload) ?: return
        if (presence.origin == nodeId) return
        markPeer(presence.origin, presence.riderName, presence.deviceName)
    }

    private fun touchPeer(id: UUID) {
        val now = System.currentTimeMillis()
        var added = false
        peers.compute(id) { _, current ->
            if (current == null) {
                added = true
                RiderPeer(id = id, riderName = "", deviceName = "", lastSeenMs = now)
            } else {
                current.copy(lastSeenMs = now)
            }
        }
        notifyPeerCount(force = added)
    }

    private fun markPeer(id: UUID, riderName: String, deviceName: String) {
        val now = System.currentTimeMillis()
        val previous = peers[id]
        val resolvedRider = riderName.ifBlank { previous?.riderName.orEmpty() }
        val resolvedDevice = deviceName.ifBlank { previous?.deviceName.orEmpty() }
        peers[id] = RiderPeer(id, resolvedRider, resolvedDevice, now)
        val identityChanged = previous == null ||
            previous.riderName != resolvedRider || previous.deviceName != resolvedDevice
        notifyPeerCount(force = identityChanged)
    }

    private fun prunePeers(now: Long) {
        peers.entries.removeIf { now - it.value.lastSeenMs > PRESENCE_TIMEOUT_MS }
        notifyPeerCount()
    }
''',
    marker='private fun touchPeer(id: UUID)',
)
replace_once(
    internet_path,
    '''    internal data class InternetPacket(
        val origin: UUID,
        val sequence: Int,
        val timestampMs: Long,
        val audio: ByteArray,
    )
''',
    '''    data class RiderPeer(
        val id: UUID,
        val riderName: String,
        val deviceName: String,
        val lastSeenMs: Long,
    ) {
        val displayName: String
            get() = riderName.ifBlank {
                deviceName.ifBlank { "Rider ${id.toString().take(4).uppercase()}" }
            }
    }

    internal data class PresencePacket(
        val origin: UUID,
        val timestampMs: Long,
        val riderName: String,
        val deviceName: String,
    )

    internal fun encodePresence(packet: PresencePacket): ByteArray {
        val riderBytes = packet.riderName.toByteArray(Charsets.UTF_8).let {
            if (it.size > MAX_RIDER_NAME_BYTES) it.copyOf(MAX_RIDER_NAME_BYTES) else it
        }
        val deviceBytes = packet.deviceName.toByteArray(Charsets.UTF_8).let {
            if (it.size > MAX_DEVICE_NAME_BYTES) it.copyOf(MAX_DEVICE_NAME_BYTES) else it
        }
        return ByteBuffer.allocate(PRESENCE_BASE_BYTES + 1 + riderBytes.size + 1 + deviceBytes.size)
            .order(ByteOrder.BIG_ENDIAN)
            .putLong(packet.origin.mostSignificantBits)
            .putLong(packet.origin.leastSignificantBits)
            .putLong(packet.timestampMs)
            .put(riderBytes.size.toByte())
            .put(riderBytes)
            .put(deviceBytes.size.toByte())
            .put(deviceBytes)
            .array()
    }

    internal fun decodePresence(payload: ByteArray): PresencePacket? {
        if (payload.size < PRESENCE_BASE_BYTES) return null
        return try {
            val buffer = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)
            val origin = UUID(buffer.long, buffer.long)
            val timestamp = buffer.long

            // Beta 1 / early Beta 1.1 presence was exactly 24 bytes. Keep it readable.
            if (!buffer.hasRemaining()) {
                return PresencePacket(origin, timestamp, "", "")
            }

            val riderLength = buffer.get().toInt() and 0xff
            if (riderLength > buffer.remaining()) return PresencePacket(origin, timestamp, "", "")
            val riderBytes = ByteArray(riderLength)
            buffer.get(riderBytes)
            val rider = riderBytes.toString(Charsets.UTF_8).trim()

            if (!buffer.hasRemaining()) {
                return PresencePacket(origin, timestamp, rider, "")
            }
            val deviceLength = buffer.get().toInt() and 0xff
            if (deviceLength > buffer.remaining()) return PresencePacket(origin, timestamp, rider, "")
            val deviceBytes = ByteArray(deviceLength)
            buffer.get(deviceBytes)
            val device = deviceBytes.toString(Charsets.UTF_8).trim()
            PresencePacket(origin, timestamp, rider, device)
        } catch (_: Throwable) {
            null
        }
    }

    private fun sanitizeIdentity(value: String, fallback: String, maxBytes: Int): String {
        val clean = value.trim().replace('|', '/').ifBlank { fallback }
        var result = clean
        while (result.toByteArray(Charsets.UTF_8).size > maxBytes && result.isNotEmpty()) {
            result = result.dropLast(1)
        }
        return result.ifBlank { fallback }
    }

    internal data class InternetPacket(
        val origin: UUID,
        val sequence: Int,
        val timestampMs: Long,
        val audio: ByteArray,
    )
''',
    marker='internal data class PresencePacket(',
)
replace_once(
    internet_path,
    'private const val PRESENCE_BYTES = 24\n        private const val MAGIC = 0x524D4931',
    'private const val PRESENCE_BASE_BYTES = 24\n        private const val MAX_RIDER_NAME_BYTES = 48\n        private const val MAX_DEVICE_NAME_BYTES = 64\n        private const val MAGIC = 0x524D4931',
    marker='private const val PRESENCE_BASE_BYTES = 24',
)

# Local mesh already advertises the rider name. Add device model metadata and expose
# a read-only direct-peer roster to MainActivity without changing the audio protocol.
mesh_path = "app/src/main/java/com/bikemesh/ridemesh/mesh/MeshNode.kt"
replace_once(
    mesh_path,
    'enum class LabRole { NORMAL, A, B, C }\n\n    interface Listener {',
    '''enum class LabRole { NORMAL, A, B, C }

    data class RiderPeer(
        val endpointId: String,
        val riderName: String,
        val deviceName: String,
    ) {
        val displayName: String
            get() = riderName.ifBlank { deviceName.ifBlank { "Rider" } }
    }

    interface Listener {''',
    marker='data class RiderPeer(',
)
replace_once(
    mesh_path,
    'private var riderName: String = "Rider"\n    private var rideCode: String = "RIDE01"',
    'private var riderName: String = "Rider"\n    private var deviceName: String = "Android device"\n    private var rideCode: String = "RIDE01"',
    marker='private var deviceName: String = "Android device"',
)
replace_once(
    mesh_path,
    'fun start(riderName: String, rideCode: String, labRole: LabRole = LabRole.NORMAL) {\n        stop()\n        this.riderName = riderName.trim().ifBlank { "Rider" }.take(18)\n        this.rideCode = rideCode.trim().uppercase().ifBlank { "RIDE01" }.take(12)',
    '''fun start(
        riderName: String,
        rideCode: String,
        labRole: LabRole = LabRole.NORMAL,
        deviceName: String = "",
    ) {
        stop()
        this.riderName = sanitizeEndpointPart(riderName).ifBlank { "Rider" }.take(18)
        this.deviceName = sanitizeEndpointPart(deviceName).ifBlank { "Android device" }.take(40)
        this.rideCode = rideCode.trim().uppercase().ifBlank { "RIDE01" }.take(12)''',
    marker='deviceName: String = "",',
)
replace_once(
    mesh_path,
    '''    fun sendLocalAudio(audio: ByteArray) {
''',
    '''    fun directPeers(): List<RiderPeer> = connected.mapNotNull { endpointId ->
        val endpointName = endpointNames[endpointId] ?: return@mapNotNull null
        RiderPeer(
            endpointId = endpointId,
            riderName = parseRiderName(endpointName),
            deviceName = parseDeviceName(endpointName),
        )
    }.sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName })

    fun sendLocalAudio(audio: ByteArray) {
''',
    marker='fun directPeers(): List<RiderPeer>',
)
replace_once(
    mesh_path,
    'private fun advertisedName(): String = "$rideCode|$riderName|${labRole.name}|${nodeId.toString().take(8)}"\n\n    private fun parseRideCode(endpointName: String): String = endpointName.substringBefore(\'|\').uppercase()',
    '''private fun advertisedName(): String =
        "$rideCode|$riderName|${labRole.name}|${nodeId.toString().take(8)}|$deviceName"

    private fun parseRideCode(endpointName: String): String = endpointName.substringBefore('|').uppercase()

    private fun parseRiderName(endpointName: String): String {
        val parts = endpointName.split('|')
        return if (parts.size >= 2) parts[1].trim() else endpointName.trim()
    }

    private fun parseDeviceName(endpointName: String): String {
        val parts = endpointName.split('|')
        return if (parts.size >= 5) parts[4].trim() else ""
    }

    private fun sanitizeEndpointPart(value: String): String = value.trim().replace('|', '/')''',
    marker='private fun parseDeviceName(endpointName: String)',
)
replace_once(
    mesh_path,
    '''    private fun displayName(endpointName: String): String {
        val parts = endpointName.split('|')
        val name = if (parts.size >= 2) parts[1] else endpointName
        val role = parseLabRole(endpointName)
        return if (role == LabRole.NORMAL) name else "$name [${role.name}]"
    }
''',
    '''    private fun displayName(endpointName: String): String {
        val name = parseRiderName(endpointName)
        val role = parseLabRole(endpointName)
        return if (role == LabRole.NORMAL) name else "$name [${role.name}]"
    }
''',
    marker='val name = parseRiderName(endpointName)',
)

# MainActivity: publish local identity, publish Internet identity, show a real roster
# when RIDERS is tapped, and put the live total directly on that button.
main_path = "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt"
replace_once(
    main_path,
    'internetNode.start(code)',
    'internetNode.start(code, rider, deviceLabel())',
    marker='internetNode.start(code, rider, deviceLabel())',
)
replace_once(
    main_path,
    '''            normalizedRideCode(),
            MeshNode.LabRole.NORMAL,
        )''',
    '''            normalizedRideCode(),
            MeshNode.LabRole.NORMAL,
            deviceLabel(),
        )''',
    marker='MeshNode.LabRole.NORMAL,\n            deviceLabel(),',
)
replace_once(
    main_path,
    'binding.homeNetworkStatus.text = "●  READY TO RIDE"\n        log("Ride stopped")',
    'binding.homeNetworkStatus.text = "●  READY TO RIDE"\n        binding.activeRiders.text = "RIDERS"\n        log("Ride stopped")',
    marker='binding.activeRiders.text = "RIDERS"',
)
replace_once(
    main_path,
    'private fun generateRideCode(): String = "RM" + Random.nextInt(1000, 9999)\n\n    private fun hasRequiredPermissions()',
    '''private fun generateRideCode(): String = "RM" + Random.nextInt(1000, 9999)

    private fun deviceLabel(): String {
        val manufacturer = Build.MANUFACTURER.trim()
            .replaceFirstChar { if (it.isLowerCase()) it.titlecase(Locale.ROOT) else it.toString() }
        val model = Build.MODEL.trim()
        return when {
            model.isBlank() -> manufacturer.ifBlank { "Android device" }
            manufacturer.isBlank() -> model
            model.startsWith(manufacturer, ignoreCase = true) -> model
            else -> "$manufacturer $model"
        }.take(48)
    }

    private fun hasRequiredPermissions()''',
    marker='private fun deviceLabel(): String',
)
replace_once(
    main_path,
    '''        binding.homeNetworkStatus.text = when {
            internetNode.isConnected() -> "●  INTERNET VOICE ACTIVE"
            directPeerCount > 0 -> "●  LOCAL MESH ACTIVE"
            else -> "●  READY TO RIDE"
        }
        applyPowerUi()
''',
    '''        binding.homeNetworkStatus.text = when {
            internetNode.isConnected() -> "●  INTERNET VOICE ACTIVE"
            directPeerCount > 0 -> "●  LOCAL MESH ACTIVE"
            else -> "●  READY TO RIDE"
        }
        val visibleRiderTotal = when {
            internetNode.isConnected() -> internetPeerCount + 1
            directPeerCount > 0 -> directPeerCount + 1
            else -> 1
        }
        binding.activeRiders.text = "RIDERS $visibleRiderTotal"
        applyPowerUi()
''',
    marker='binding.activeRiders.text = "RIDERS $visibleRiderTotal"',
)
replace_once(
    main_path,
    '''    private fun showRidersDialog() {
        val internetTotal = if (internetNode.isConnected()) internetPeerCount + 1 else 0

        val message = buildString {
            if (internetNode.isConnected()) {
                append("Internet group: $internetTotal rider${if (internetTotal == 1) "" else "s"}\\n")
            }
            append("Nearby direct peers: $directPeerCount\\n")
            append("Local mesh: ${if (meshRunning) "ready" else "sleeping"}\\n")
            append("Noise reduction: ON\\n")
            append("Auto reconnect: ON\\n\\n")
            append("Use INVITE to add riders without ending the conversation.")
        }

        AlertDialog.Builder(this)
            .setTitle("Riders")
            .setMessage(message)
            .setPositiveButton("INVITE") { _, _ -> showLiveInviteOptions() }
            .setNegativeButton("CLOSE", null)
            .show()
    }
''',
    '''    private fun showRidersDialog() {
        val me = binding.riderName.text?.toString().orEmpty().ifBlank { Build.MODEL.take(18) }
        val meDevice = deviceLabel()
        val internetPeers = if (internetNode.isConnected()) internetNode.remotePeers() else emptyList()
        val localPeers = if (meshRunning) meshNode.directPeers() else emptyList()
        val riderLines = linkedMapOf<String, String>()

        internetPeers.forEach { peer ->
            val device = peer.deviceName.ifBlank { "Android device" }
            val key = "${peer.displayName}|$device".lowercase(Locale.ROOT)
            riderLines[key] = "• ${peer.displayName}\\n  $device • Internet"
        }

        localPeers.forEach { peer ->
            val device = peer.deviceName.ifBlank { "Android device" }
            val key = "${peer.displayName}|$device".lowercase(Locale.ROOT)
            if (!riderLines.containsKey(key)) {
                riderLines[key] = "• ${peer.displayName}\\n  $device • Local mesh"
            }
        }

        val message = buildString {
            append("YOU\\n")
            append("• $me\\n")
            append("  $meDevice\\n\\n")

            append("CONNECTED RIDERS")
            if (riderLines.isEmpty()) {
                append("\\nWaiting for another rider…")
            } else {
                append(" (${riderLines.size})\\n")
                append(riderLines.values.joinToString("\\n\\n"))
            }

            append("\\n\\nPath: ")
            append(
                when {
                    internetNode.isConnected() -> "Internet"
                    directPeerCount > 0 -> "Local mesh"
                    else -> "Reconnecting"
                }
            )
            append(" • Auto reconnect ON")
        }

        AlertDialog.Builder(this)
            .setTitle("Riders • ${riderLines.size + 1} total")
            .setMessage(message)
            .setPositiveButton("INVITE") { _, _ -> showLiveInviteOptions() }
            .setNegativeButton("CLOSE", null)
            .show()
    }
''',
    marker='CONNECTED RIDERS',
)

# Make the existing chosen cyan/white RideMesh mark occupy more of the launcher mask.
replace_once(
    "app/src/main/res/drawable/ic_launcher_foreground.xml",
    'android:top="16dp" android:bottom="16dp" android:left="16dp" android:right="16dp"',
    'android:top="8dp" android:bottom="8dp" android:left="8dp" android:right="8dp"',
    marker='android:top="8dp" android:bottom="8dp"',
)
replace_once(
    "app/src/main/res/mipmap-anydpi/ic_launcher.xml",
    'android:top="10dp" android:bottom="10dp" android:left="10dp" android:right="10dp"',
    'android:top="6dp" android:bottom="6dp" android:left="6dp" android:right="6dp"',
    marker='android:top="6dp" android:bottom="6dp"',
)
replace_once(
    "app/src/main/res/mipmap-anydpi/ic_launcher_round.xml",
    'android:top="10dp" android:bottom="10dp" android:left="10dp" android:right="10dp"',
    'android:top="6dp" android:bottom="6dp" android:left="6dp" android:right="6dp"',
    marker='android:top="6dp" android:bottom="6dp"',
)

# Regression coverage for rider/device presence metadata and legacy 24-byte presence.
test_path = "app/src/test/java/com/bikemesh/ridemesh/transport/InternetNodeTest.kt"
replace_once(
    test_path,
    'import org.junit.Assert.assertNotNull\nimport org.junit.Test\nimport java.util.UUID',
    'import org.junit.Assert.assertNotNull\nimport org.junit.Assert.assertTrue\nimport org.junit.Test\nimport java.nio.ByteBuffer\nimport java.nio.ByteOrder\nimport java.util.UUID',
    marker='import org.junit.Assert.assertTrue',
)
replace_once(
    test_path,
    '''    @Test
    fun encodedPacketHasExact33ByteHeaderAndRoundTripsAudio() {''',
    '''    @Test
    fun presenceCarriesRiderAndDeviceAndKeepsLegacyPrefix() {
        val node = InternetNode(listener)
        val id = UUID.fromString("87654321-4321-6789-4321-678987654321")
        val presence = InternetNode.PresencePacket(
            origin = id,
            timestampMs = 1_725_000_000_123L,
            riderName = "Rahul",
            deviceName = "Google Pixel 8",
        )

        val encoded = node.encodePresence(presence)
        assertTrue(encoded.size > 24)
        val prefix = ByteBuffer.wrap(encoded, 0, 24).order(ByteOrder.BIG_ENDIAN)
        assertEquals(id, UUID(prefix.long, prefix.long))
        assertEquals(presence.timestampMs, prefix.long)

        val decoded = node.decodePresence(encoded)
        assertNotNull(decoded)
        assertEquals("Rahul", decoded!!.riderName)
        assertEquals("Google Pixel 8", decoded.deviceName)
    }

    @Test
    fun legacy24BytePresenceStillDecodes() {
        val node = InternetNode(listener)
        val id = UUID.fromString("11111111-2222-3333-4444-555555555555")
        val legacy = ByteBuffer.allocate(24).order(ByteOrder.BIG_ENDIAN)
            .putLong(id.mostSignificantBits)
            .putLong(id.leastSignificantBits)
            .putLong(99L)
            .array()

        val decoded = node.decodePresence(legacy)
        assertNotNull(decoded)
        assertEquals(id, decoded!!.origin)
        assertEquals("", decoded.riderName)
        assertEquals("", decoded.deviceName)
    }

    @Test
    fun encodedPacketHasExact33ByteHeaderAndRoundTripsAudio() {''',
    marker='fun presenceCarriesRiderAndDeviceAndKeepsLegacyPrefix()',
)

print("RideMesh rider roster + launcher icon patch applied")
