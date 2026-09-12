package com.bikemesh.ridemesh.transport

import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.security.MessageDigest

/**
 * RideMesh Wi-Fi Aware wire contract shared with the future iOS implementation.
 *
 * Android advertises SERVICE_NAME through WifiAware. On iOS the equivalent
 * Network/Wi-Fi Aware service is APPLE_SERVICE_FQDN. Once a peer-to-peer IP
 * path exists, both platforms use the same framed TCP protocol below.
 *
 * Frame format (network byte order):
 *   uint32 payloadLength
 *   uint8  frameType
 *   bytes  body
 */
object WifiAwareWireProtocol {
    const val SERVICE_NAME = "ridemesh"
    const val APPLE_SERVICE_FQDN = "_ridemesh._tcp"
    const val TCP_PORT = 49355
    const val PROTOCOL_VERSION = 1
    const val MAX_FRAME_BYTES = 256 * 1024

    const val TYPE_HELLO: Byte = 1
    const val TYPE_DATA: Byte = 2
    const val TYPE_PING: Byte = 3
    const val TYPE_PONG: Byte = 4

    private const val DISCOVERY_MAGIC = "RMA1"
    private const val IDENTITY_MAGIC = "RMESH1"

    data class Identity(
        val nodeId: String,
        val rideToken: String,
        val riderName: String,
    )

    enum class DiscoveryMessageKind(val wire: String) {
        IDENTITY("I"),
        HELLO("H"),
        READY("R");

        companion object {
            fun fromWire(value: String): DiscoveryMessageKind? =
                entries.firstOrNull { it.wire == value }
        }
    }

    data class DiscoveryMessage(
        val kind: DiscoveryMessageKind,
        val identity: Identity,
    )

    fun rideToken(rideCode: String): String {
        val normalized = rideCode.trim().uppercase()
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(normalized.toByteArray(Charsets.UTF_8))
        return digest.take(8).joinToString("") { "%02x".format(it) }
    }

    fun encodeDiscovery(kind: DiscoveryMessageKind, identity: Identity): ByteArray =
        listOf(
            DISCOVERY_MAGIC,
            kind.wire,
            safe(identity.nodeId, 48),
            safe(identity.rideToken, 32),
            safe(identity.riderName, 32),
        ).joinToString("|").toByteArray(Charsets.UTF_8)

    fun decodeDiscovery(bytes: ByteArray?): DiscoveryMessage? {
        if (bytes == null || bytes.isEmpty() || bytes.size > 240) return null
        val parts = bytes.toString(Charsets.UTF_8).split('|', limit = 5)
        if (parts.size != 5 || parts[0] != DISCOVERY_MAGIC) return null
        val kind = DiscoveryMessageKind.fromWire(parts[1]) ?: return null
        val nodeId = parts[2].takeIf { it.isNotBlank() } ?: return null
        val rideToken = parts[3].takeIf { it.isNotBlank() } ?: return null
        return DiscoveryMessage(
            kind = kind,
            identity = Identity(nodeId, rideToken, parts[4]),
        )
    }

    fun encodeIdentity(identity: Identity): ByteArray =
        listOf(
            IDENTITY_MAGIC,
            PROTOCOL_VERSION.toString(),
            safe(identity.nodeId, 48),
            safe(identity.rideToken, 32),
            safe(identity.riderName, 32),
        ).joinToString("|").toByteArray(Charsets.UTF_8)

    fun decodeIdentity(bytes: ByteArray): Identity? {
        val parts = bytes.toString(Charsets.UTF_8).split('|', limit = 5)
        if (parts.size != 5 || parts[0] != IDENTITY_MAGIC) return null
        if (parts[1].toIntOrNull() != PROTOCOL_VERSION) return null
        val nodeId = parts[2].takeIf { it.isNotBlank() } ?: return null
        val rideToken = parts[3].takeIf { it.isNotBlank() } ?: return null
        return Identity(nodeId, rideToken, parts[4])
    }

    fun writeFrame(output: DataOutputStream, type: Byte, body: ByteArray = byteArrayOf()) {
        require(body.size + 1 <= MAX_FRAME_BYTES) { "RideMesh frame too large" }
        synchronized(output) {
            output.writeInt(body.size + 1)
            output.writeByte(type.toInt())
            output.write(body)
            output.flush()
        }
    }

    fun readFrame(input: DataInputStream): Pair<Byte, ByteArray>? {
        val length = try {
            input.readInt()
        } catch (_: EOFException) {
            return null
        }
        if (length !in 1..MAX_FRAME_BYTES) {
            throw IllegalStateException("Invalid RideMesh frame length: $length")
        }
        val type = input.readByte()
        val body = ByteArray(length - 1)
        input.readFully(body)
        return type to body
    }

    fun encodeLong(value: Long): ByteArray = ByteArray(8) { index ->
        ((value ushr (56 - index * 8)) and 0xffL).toByte()
    }

    fun decodeLong(bytes: ByteArray): Long? {
        if (bytes.size != 8) return null
        var value = 0L
        for (byte in bytes) {
            value = (value shl 8) or (byte.toLong() and 0xffL)
        }
        return value
    }

    private fun safe(value: String, maxLength: Int): String = value
        .replace('|', '-')
        .replace('\n', ' ')
        .replace('\r', ' ')
        .trim()
        .take(maxLength)
}
