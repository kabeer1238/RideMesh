package com.bikemesh.ridemesh.offline

import org.junit.Assert.*
import org.junit.Test

class FreshAudioQueueTest {
    @Test fun shortTransferDelayPreservesSpeechOrder() {
        val q = FreshAudioQueue()
        repeat(4) { q.offer("a", byteArrayOf(it.toByte()), it * 20L) }
        repeat(4) { assertEquals(it.toByte(), q.poll(80)[0]) }
        assertEquals(0L, q.droppedCount())
    }
    @Test fun stalledLinkDropsOldSpeechAndRemainsBounded() {
        val q = FreshAudioQueue()
        repeat(100) { q.offer("a", byteArrayOf(it.toByte()), it * 20L) }
        assertEquals(6, q.size())
        assertEquals(94L, q.droppedCount())
        assertEquals(94.toByte(), q.poll(2000)[0])
        assertNull(q.poll(2200))
        assertEquals(99L, q.droppedCount())
    }
    @Test fun continuousSpeakerCannotStarveOthers() {
        val q = FreshAudioQueue()
        repeat(6) { q.offer("a", byteArrayOf(it.toByte()), 0) }
        q.offer("b", byteArrayOf(99), 0)
        assertEquals(0.toByte(), q.poll(10)[0])
        assertEquals(99.toByte(), q.poll(10)[0])
        assertEquals(1.toByte(), q.poll(10)[0])
    }
}
