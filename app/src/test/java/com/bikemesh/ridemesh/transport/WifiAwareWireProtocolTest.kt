package com.bikemesh.ridemesh.transport

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.DataOutputStream
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class WifiAwareWireProtocolTest {
    @Test
    fun discoveryRoundTripPreservesIdentity() {
        val identity = WifiAwareWireProtocol.Identity(
            nodeId = "android-node-1",
            rideToken = WifiAwareWireProtocol.rideToken("RIDE123"),
            riderName = "Rider One",
        )

        val encoded = WifiAwareWireProtocol.encodeDiscovery(
            WifiAwareWireProtocol.DiscoveryMessageKind.HELLO,
            identity,
        )
        val decoded = WifiAwareWireProtocol.decodeDiscovery(encoded)

        assertNotNull(decoded)
        assertEquals(WifiAwareWireProtocol.DiscoveryMessageKind.HELLO, decoded?.kind)
        assertEquals(identity, decoded?.identity)
    }

    @Test
    fun rideTokenDoesNotExposeRideCodeAndIsStable() {
        val first = WifiAwareWireProtocol.rideToken("Ride-42")
        val second = WifiAwareWireProtocol.rideToken(" ride-42 ")
        val other = WifiAwareWireProtocol.rideToken("Ride-43")

        assertEquals(first, second)
        assertNotEquals(first, other)
        assertNotEquals("RIDE-42", first)
        assertEquals(16, first.length)
    }

    @Test
    fun framedPayloadRoundTrips() {
        val payload = "hello-ios".toByteArray()
        val sink = ByteArrayOutputStream()
        val output = DataOutputStream(sink)

        WifiAwareWireProtocol.writeFrame(output, WifiAwareWireProtocol.TYPE_DATA, payload)

        val input = DataInputStream(ByteArrayInputStream(sink.toByteArray()))
        val frame = WifiAwareWireProtocol.readFrame(input)
        assertNotNull(frame)
        assertEquals(WifiAwareWireProtocol.TYPE_DATA, frame?.first)
        assertArrayEquals(payload, frame?.second)
    }

    @Test
    fun longEncodingRoundTrips() {
        val original = 9_876_543_210L
        assertEquals(original, WifiAwareWireProtocol.decodeLong(WifiAwareWireProtocol.encodeLong(original)))
    }
}
