package com.bikemesh.ridemesh.offline

import org.junit.Assert.*
import org.junit.Test
import java.util.UUID
import java.util.ArrayDeque

class OfflineMeshTest {
    @Test fun allSixOriginsCrossFiveLinksExactlyOnce() {
        for (source in 0..5) exercise(source, false)
    }
    @Test fun ringDuplicatesDoNotPlayTwice() {
        for (source in 0..5) exercise(source, true)
    }
    private fun exercise(source: Int, ring: Boolean) {
        val ids = List(6) { UUID.randomUUID() }
        val received = IntArray(6)
        data class Delivery(val from: Int, val to: Int, val bytes: ByteArray)
        val queue = ArrayDeque<Delivery>()
        val routers = ids.mapIndexed { i, id ->
            MeshRelayRouter(id, { exclude, bytes ->
                var sent = false
                for (j in 0..5) {
                    if ((kotlin.math.abs(i-j)==1 || (ring && kotlin.math.abs(i-j)==5)) && ids[j].toString()!=exclude) {
                        queue.add(Delivery(i,j,bytes)); sent=true
                    }
                }
                sent
            }, { if (it.type==RideMeshEnvelope.Type.AUDIO) received[i]++ }, {})
        }
        routers[source].originateAudio(byteArrayOf(1))
        var deliveries=0
        while(queue.isNotEmpty()) {
            assertTrue("Flood must terminate", ++deliveries<100)
            val d=queue.remove(); routers[d.to].receive(ids[d.from].toString(),d.bytes)
        }
        for(i in 0..5) assertEquals(if(i==source)0 else 1,received[i])
    }
    @Test fun opusRoundTripAndIndependentDecoders() {
        val codec=OpusVoiceCodec()
        repeat(8) { frame ->
            val pcm=ByteArray(640)
            for (i in 0 until 320) {
                val v=(8000*kotlin.math.sin(2*Math.PI*440*(frame*320+i)/16000)).toInt()
                pcm[i*2]=v.toByte();pcm[i*2+1]=(v shr 8).toByte()
            }
            val encoded=codec.encode20ms(pcm)
            assertNotNull(encoded)
            for (rider in 1..5) assertEquals(640,codec.decode20ms("rider$rider",encoded!!)!!.size)
        }
        assertEquals(640,codec.conceal20ms("rider1")!!.size)
    }
    @Test fun malformedEnvelopeIsRejected() {
        assertNull(RideMeshEnvelope.decode(ByteArray(71)))
        val id=UUID.randomUUID()
        val good=RideMeshEnvelope.newDiagnostic(id,1,"probe").encode()
        assertNotNull(RideMeshEnvelope.decode(good))
        assertNull(RideMeshEnvelope.decode(good.copyOf(good.size-1)))
    }
}
