from pathlib import Path

p = Path('app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt')
s = p.read_text()

if 'import org.json.JSONObject' not in s:
    s = s.replace('import org.webrtc.AudioSource\n', 'import org.json.JSONObject\nimport org.webrtc.AudioSource\n', 1)

old_receive = '''            locationTopic -> decodeLocation(payload)?.let { location ->\n                if (location.riderId != nodeId) listener.onInternetRiderLocation(location)\n            }\n'''
new_receive = '''            locationTopic -> decodeLocationCompat(payload)?.let { location ->\n                if (location.riderId != nodeId) listener.onInternetRiderLocation(location)\n            }\n'''
if 'locationTopic -> decodeLocationCompat(payload)' not in s:
    if old_receive not in s:
        raise SystemExit('location receive anchor not found')
    s = s.replace(old_receive, new_receive, 1)

if 'private fun decodeLocationCompat(payload: ByteArray)' not in s:
    anchor = '    private fun sanitizePhone(value: String): String = value\n'
    compat = r'''    /**
     * Android uses the compact RML1 binary packet. The iOS beta can publish the
     * same room-scoped location as JSON, so accept both representations here.
     * This keeps Android/Android behavior unchanged while making iPhone riders
     * visible on Android maps.
     */
    private fun decodeLocationCompat(payload: ByteArray): RiderLocation? {
        decodeLocation(payload)?.let { return it }
        return decodeJsonLocation(payload)
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
print('Beta5.2 iOS/Android location compatibility applied')
