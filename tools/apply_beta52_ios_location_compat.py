from pathlib import Path

# Beta5.2.1 — canonical iOS RML1 location receive compatibility.
#
# The existing Android Beta5.2 map encoder has an Android-only extension after
# the display name (phone length + phone bytes). iOS vc23/vc24 intentionally
# publishes the canonical RML1 v1 packet without that extension:
#
# RML1 | v1 | UUID | timestamp | lat | lon | speed | heading | quality(0..3)
#      | nameLength | UTF-8 displayName
#
# Android already publishes on the same room-scoped location topic and iOS is
# lenient about Android's trailing extension, which is why Android -> iOS works.
# This patch makes Android accept both formats, without changing voice/signaling
# or breaking Android -> Android map compatibility.

p = Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt')
s = p.read_text()

if 'import org.json.JSONObject' not in s:
    s = s.replace('import org.webrtc.AudioSource\n', 'import org.json.JSONObject\nimport org.webrtc.AudioSource\n', 1)

old_receive = '''            locationTopic -> decodeLocation(payload)?.let { location ->
                if (location.riderId != nodeId) listener.onInternetRiderLocation(location)
            }
'''
new_receive = '''            locationTopic -> decodeLocationCompat(payload)?.let { location ->
                if (location.riderId != nodeId) listener.onInternetRiderLocation(location)
            }
'''
if 'locationTopic -> decodeLocationCompat(payload)' not in s:
    if old_receive not in s:
        raise SystemExit('location receive anchor not found')
    s = s.replace(old_receive, new_receive, 1)

if 'private fun decodeCanonicalRml1Location(payload: ByteArray)' not in s:
    anchor = '    private fun sanitizePhone(value: String): String = value\n'
    compat = r'''    /**
     * Accept all location representations currently used by RideMesh:
     * 1) Android Beta5.x extended RML1 (existing decoder, includes phone tail)
     * 2) Canonical RML1 v1 used by iOS vc23/vc24 (no phone tail)
     * 3) JSON fallback retained for older experimental iOS builds
     *
     * Voice/signaling is not touched by this compatibility path.
     */
    private fun decodeLocationCompat(payload: ByteArray): RiderLocation? {
        decodeLocation(payload)?.let { return it }
        decodeCanonicalRml1Location(payload)?.let { return it }
        return decodeJsonLocation(payload)
    }

    private fun decodeCanonicalRml1Location(payload: ByteArray): RiderLocation? {
        // 55 bytes is the fixed canonical RML1 header including name-length byte.
        if (payload.size < 55) return null
        return try {
            val buffer = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)
            if (buffer.int != 0x524D4C31 || buffer.get().toInt() != 1) return null

            val riderId = UUID(buffer.long, buffer.long)
            val timestampMs = buffer.long
            val latitude = buffer.double
            val longitude = buffer.double
            val speedKmh = buffer.float
            val heading = buffer.float
            val qualityRaw = buffer.get().toInt() and 0xff
            val nameLength = buffer.get().toInt() and 0xff

            if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0) return null
            if (!latitude.isFinite() || !longitude.isFinite()) return null
            if (nameLength > 48 || buffer.remaining() < nameLength) return null

            val nameBytes = ByteArray(nameLength)
            buffer.get(nameBytes)

            // Canonical iOS RML1 v1 quality values:
            // 0=excellent, 1=good, 2=poor, 3=reconnecting.
            val quality = when (qualityRaw) {
                0 -> "Excellent"
                1 -> "Good"
                2 -> "Poor"
                3 -> "Reconnecting"
                else -> "Good"
            }

            RiderLocation(
                riderId = riderId,
                displayName = nameBytes.toString(Charsets.UTF_8).trim().ifBlank { "Rider" },
                latitude = latitude,
                longitude = longitude,
                speedKmh = speedKmh.coerceIn(0f, 450f),
                heading = ((heading % 360f) + 360f) % 360f,
                timestampMs = timestampMs,
                connectionQuality = quality,
                phoneNumber = "",
            )
        } catch (_: Throwable) {
            null
        }
    }

    private fun decodeJsonLocation(payload: ByteArray): RiderLocation? {
        val text = payload.toString(Charsets.UTF_8).trim()
        if (!text.startsWith("{")) return null
        return try {
            val root = JSONObject(text)
            val location = root.optJSONObject("location") ?: root
            val rider = root.optJSONObject("rider") ?: root

            fun firstString(source: JSONObject, vararg keys: String): String {
                keys.forEach { key ->
                    if (source.has(key) && !source.isNull(key)) {
                        val value = source.optString(key, "").trim()
                        if (value.isNotBlank()) return value
                    }
                }
                return ""
            }

            fun firstDouble(source: JSONObject, vararg keys: String): Double? {
                keys.forEach { key ->
                    if (source.has(key) && !source.isNull(key)) {
                        val value = source.opt(key)
                        val parsed = when (value) {
                            is Number -> value.toDouble()
                            is String -> value.toDoubleOrNull()
                            else -> null
                        }
                        if (parsed != null && parsed.isFinite()) return parsed
                    }
                }
                return null
            }

            val idText = firstString(
                rider,
                "riderId", "riderID", "rider_id", "nodeId", "nodeID", "id", "origin"
            ).ifBlank {
                firstString(root, "riderId", "riderID", "rider_id", "nodeId", "nodeID", "id", "origin")
            }
            val riderId = runCatching { UUID.fromString(idText) }.getOrNull() ?: return null

            val latitude = firstDouble(location, "latitude", "lat") ?: return null
            val longitude = firstDouble(location, "longitude", "lng", "lon", "long") ?: return null
            if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0) return null

            val speed = (firstDouble(location, "speedKmh", "speedKPH", "speedKph", "speed") ?: 0.0)
                .toFloat().coerceIn(0f, 450f)
            val heading = (firstDouble(location, "heading", "bearing", "course") ?: 0.0)
                .toFloat().let { ((it % 360f) + 360f) % 360f }

            var timestamp = (firstDouble(location, "timestampMs", "timestamp", "time", "ts")
                ?: firstDouble(root, "timestampMs", "timestamp", "time", "ts")
                ?: System.currentTimeMillis().toDouble()).toLong()
            if (timestamp in 1..9_999_999_999L) timestamp *= 1_000L

            val displayName = firstString(rider, "displayName", "riderName", "name")
                .ifBlank { firstString(root, "displayName", "riderName", "name") }
                .ifBlank { "Rider" }
                .take(24)
            val quality = firstString(location, "connectionQuality", "quality")
                .ifBlank { firstString(root, "connectionQuality", "quality") }
                .ifBlank { "Good" }
            val phone = firstString(rider, "phoneNumber", "phone")
                .ifBlank { firstString(root, "phoneNumber", "phone") }

            RiderLocation(
                riderId = riderId,
                displayName = displayName,
                latitude = latitude,
                longitude = longitude,
                speedKmh = speed,
                heading = heading,
                timestampMs = timestamp,
                connectionQuality = quality,
                phoneNumber = sanitizePhone(phone),
            )
        } catch (_: Throwable) {
            null
        }
    }

'''
    if anchor not in s:
        raise SystemExit('sanitizePhone anchor not found')
    s = s.replace(anchor, compat + anchor, 1)

p.write_text(s)

# Give this field-test APK its own Android version code/name so it can cleanly
# replace the prior Beta5.2 vc20 build on devices.
gradle = Path('app/build.gradle.kts')
g = gradle.read_text()
g = g.replace('versionCode = 20', 'versionCode = 21')
g = g.replace(
    'versionName = "1.0.0-beta5.2-clean-shutdown-map"',
    'versionName = "1.0.0-beta5.2.1-ios-rml1-location"',
)
gradle.write_text(g)

print('Beta5.2.1 canonical iOS RML1 -> Android location compatibility applied')
