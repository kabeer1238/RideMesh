package com.bikemesh.ridemesh.location

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets
import java.util.UUID

data class RideLocationPacket(
    val riderId: UUID,
    val displayName: String,
    val latitude: Double,
    val longitude: Double,
    val speedKmh: Float,
    val heading: Float,
    val timestampMs: Long,
    val connectionQuality: Int, // 1 excellent, 2 good, 3 poor, 4 reconnecting
    val phoneNumber: String = "",
)

/** RML1 extended reference used by iOS vc25 and Android Beta5.x. */
object RideLocationCodec {
    private const val MAGIC = 0x524D4C31 // RML1
    private const val VERSION: Byte = 1
    private const val MAX_NAME = 48
    private const val MAX_PHONE = 32
    private const val FIXED_BYTES = 56

    fun encode(packet: RideLocationPacket): ByteArray {
        val name = packet.displayName.toByteArray(StandardCharsets.UTF_8).let {
            if (it.size <= MAX_NAME) it else it.copyOf(MAX_NAME)
        }
        val phone = packet.phoneNumber.toByteArray(StandardCharsets.UTF_8).let {
            if (it.size <= MAX_PHONE) it else it.copyOf(MAX_PHONE)
        }
        return ByteBuffer.allocate(FIXED_BYTES + name.size + phone.size).order(ByteOrder.BIG_ENDIAN).apply {
            putInt(MAGIC)
            put(VERSION)
            putLong(packet.riderId.mostSignificantBits)
            putLong(packet.riderId.leastSignificantBits)
            putLong(packet.timestampMs)
            putDouble(packet.latitude)
            putDouble(packet.longitude)
            putFloat(packet.speedKmh.coerceAtLeast(0f))
            putFloat(packet.heading)
            put(packet.connectionQuality.coerceIn(1, 4).toByte())
            put(name.size.toByte())
            put(name)
            put(phone.size.toByte())
            put(phone)
        }.array()
    }
}
