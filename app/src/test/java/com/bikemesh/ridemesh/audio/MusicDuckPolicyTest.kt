package com.bikemesh.ridemesh.audio

import org.junit.Assert.*
import org.junit.Test

class MusicDuckPolicyTest {
    @Test fun stabilizesThenDucksAndRestoresAfterSilence() {
        val p = MusicDuckPolicy()
        assertNull(p.tick(10, true, true, 0))
        assertNull(p.tick(10, true, true, 599))
        assertEquals(2, p.tick(10, true, true, 600))
        assertNull(p.tick(2, true, false, 1500))
        assertEquals(3, p.tick(2, true, false, 1600))
        assertEquals(4, p.tick(3, true, false, 1700))
        assertEquals(10, p.release(4))
    }
    @Test fun riderVolumeChangeIsNeverRestoredToStaleValue() {
        val p = MusicDuckPolicy()
        p.tick(10, true, false, 0)
        assertEquals(2, p.tick(10, true, true, 600))
        assertNull(p.tick(7, true, true, 700))
        assertNull(p.tick(7, true, false, 2000))
        assertNull(p.release(7))
    }
    @Test fun interruptionRestoresOnlyVolumeOwnedByRideMesh() {
        val p = MusicDuckPolicy()
        p.tick(10, true, false, 0)
        p.tick(10, true, true, 600)
        assertNull(p.release(5)) // rider adjusted before the next poll
        p.tick(10, true, false, 2000)
        p.tick(10, true, true, 2600)
        assertEquals(10, p.release(2))
        assertNull(p.release(10))
    }
    @Test fun quietMusicAndMinimumVolumeAreUntouched() {
        val p = MusicDuckPolicy()
        p.tick(1, true, false, 0)
        assertNull(p.tick(1, true, true, 600))
        assertNull(p.tick(5, true, false, 1600))
        assertNull(p.release(5))
    }
}
