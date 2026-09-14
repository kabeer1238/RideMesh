package com.bikemesh.ridemesh.audio

import org.junit.Assert.*
import org.junit.Test

class PcmChunkerTest {
    @Test fun preservesSequentialBytesAcrossRideMeshFrames() {
        val chunker = PcmChunker(8)
        val chunks = mutableListOf<ByteArray>()
        chunker.push(byteArrayOf(0, 1, 2, 3, 4, 5)) { chunks += it }
        assertTrue(chunks.isEmpty())
        chunker.push(byteArrayOf(6, 7, 8, 9, 10, 11)) { chunks += it }
        assertEquals(1, chunks.size)
        assertArrayEquals(byteArrayOf(0, 1, 2, 3, 4, 5, 6, 7), chunks[0])
        chunker.push(byteArrayOf(12, 13, 14, 15)) { chunks += it }
        assertEquals(2, chunks.size)
        assertArrayEquals(byteArrayOf(8, 9, 10, 11, 12, 13, 14, 15), chunks[1])
    }

    @Test fun callbackFailureDoesNotStallFollowingAudio() {
        val chunker = PcmChunker(2)
        runCatching { chunker.push(byteArrayOf(1, 2)) { error("inference") } }
        val chunks = mutableListOf<ByteArray>()
        chunker.push(byteArrayOf(3, 4)) { chunks += it }
        assertArrayEquals(byteArrayOf(3, 4), chunks.single())
    }

    @Test fun clearPreventsAudioFromCrossingPrivacyBoundary() {
        val chunker = PcmChunker(4)
        val chunks = mutableListOf<ByteArray>()
        chunker.push(byteArrayOf(1, 2)) { chunks += it }
        chunker.clear()
        chunker.push(byteArrayOf(3, 4, 5, 6)) { chunks += it }
        assertEquals(1, chunks.size)
        assertArrayEquals(byteArrayOf(3, 4, 5, 6), chunks[0])
    }
}
