package com.bikemesh.ridemesh.transport

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID

class InternetNodeTest {
    private val listener = object : InternetNode.Listener {
        override fun onInternetState(connected: Boolean, message: String) = Unit
        override fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) = Unit
        override fun onInternetPeerCount(count: Int) = Unit
    }

    @Test
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
    fun encodedPacketHasExact33ByteHeaderAndRoundTripsAudio() {
        val node = InternetNode(listener)
        val audio = ByteArray(640) { index -> (index and 0xff).toByte() }
        val packet = InternetNode.InternetPacket(
            origin = UUID.fromString("12345678-1234-5678-1234-567812345678"),
            sequence = 42,
            timestampMs = 1_725_000_000_000L,
            audio = audio,
        )

        val encoded = node.encode(packet)
        assertEquals(33 + audio.size, encoded.size)
        val decoded = node.decode(encoded)
        assertNotNull(decoded)
        assertEquals(packet.origin, decoded!!.origin)
        assertEquals(packet.sequence, decoded.sequence)
        assertEquals(packet.timestampMs, decoded.timestampMs)
        assertArrayEquals(audio, decoded.audio)
    }
}
