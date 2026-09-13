package com.bikemesh.ridemesh.offline

import org.junit.Assert.*
import org.junit.Test
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.sin

class OpusVoiceCodecTest {
    @Test fun nativeFloatOpusPacketsDecodeOnAndroid() {
        // Generated using libopus opus_encode_float: VOIP, 16 kHz mono,
        // 20 ms, 440 Hz at amplitude 0.08; wrapped with the iOS OPV1 header.
        val fixtures = listOf(
            "T1BWMQEARUiBe4KRdvR1AAADR+yKmlbSzVaN2BmSKy2/gnVtF0PW4MMsYODnGqOIGOMbk2l6YIe14xuV9vUCu+NCYwyKPjUlUdgKQA==",
            "T1BWMQEANEic1heslQDvpu+GmjTEg1BQIE/lA+r8i8CpZ0qdDzq2yXZy9RDurd3HPkzsBm2sXn24gQU=",
            "T1BWMQEAKkiZSh91nPxLVRJ80MsW/gwFDwkRFFVm6CSb7D54CVvYz745HF5NrF/oUA==",
            "T1BWMQEAMEiZSh91mEp9p15+i+SkSoAUfXsj1DmPliVOG27mbYvGZ6D66XAW61ExR6Er9/sNgA==",
            "T1BWMQEALkiZSh91nPxJM7JZyxEi996YMHP4nX0bVyihS/40/KnUockdzihMG8e/9SPmxkA="
        )
        val codec = OpusVoiceCodec()
        var energy = 0L
        for (fixture in fixtures) {
            val decoded = codec.decode20ms("native", java.util.Base64.getDecoder().decode(fixture)) ?: error("Native packet rejected")
            assertEquals(640, decoded.size)
            val samples = ByteBuffer.wrap(decoded).order(ByteOrder.LITTLE_ENDIAN)
            while (samples.hasRemaining()) { val s = samples.short.toLong(); energy += s*s }
        }
        assertTrue("Native float Opus must produce audible PCM", energy > 1600L*100*100)
    }
    @Test fun toneSurvivesWireCodecWithAudibleEnergy() {
        val sender = OpusVoiceCodec()
        val receiver = OpusVoiceCodec()
        var energy = 0L
        repeat(10) { frame ->
            val pcm = ByteBuffer.allocate(640).order(ByteOrder.LITTLE_ENDIAN)
            repeat(320) { i -> pcm.putShort((2600 * sin(2 * Math.PI * 440 * (frame * 320 + i) / 16000)).toInt().toShort()) }
            val packet = sender.encode20ms(pcm.array()) ?: error("Opus encode failed")
            assertTrue(packet.size in 8..263)
            val decoded = receiver.decode20ms("sender", packet) ?: error("Opus decode failed")
            assertEquals(640, decoded.size)
            val samples = ByteBuffer.wrap(decoded).order(ByteOrder.LITTLE_ENDIAN)
            while (samples.hasRemaining()) { val s = samples.short.toLong(); energy += s*s }
        }
        assertTrue("Decoded tone must not be silence", energy > 3200L * 100 * 100)
    }

    @Test fun malformedLengthDoesNotProduceAudio() {
        val codec = OpusVoiceCodec()
        val packet = codec.encode20ms(ByteArray(640)) ?: error("Encode failed")
        packet[6] = 0
        assertNull(codec.decode20ms("sender", packet))
    }
}
