package com.bikemesh.ridemesh.transport

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import java.util.UUID

class InternetNodeTest {
    private val listener = object : InternetNode.Listener {
        override fun onInternetState(connected: Boolean, message: String) = Unit
        override fun onInternetAudio(audio: ByteArray) = Unit
        override fun onInternetPeerCount(count: Int) = Unit
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
