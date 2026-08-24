package com.bikemesh.ridemesh.beta

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class BetaWindowTest {
    private val start = 1_700_000_000_000L

    @Test fun startsWithSixtyDays() {
        assertEquals(60L, BetaWindow.remainingDays(start, start))
        assertFalse(BetaWindow.isExpired(start, start))
    }

    @Test fun expiresAtExactlySixtyDays() {
        val expiry = start + BetaWindow.DURATION_MS
        assertEquals(0L, BetaWindow.remainingDays(start, expiry))
        assertTrue(BetaWindow.isExpired(start, expiry))
    }

    @Test fun partialDayRoundsUpForUserCountdown() {
        val now = start + 59L * BetaWindow.DAY_MS + 1L
        assertEquals(1L, BetaWindow.remainingDays(start, now))
    }

    @Test fun warningBucketsMatchReleasePlan() {
        assertEquals(14, BetaWindow.warningBucket(14))
        assertEquals(7, BetaWindow.warningBucket(7))
        assertEquals(3, BetaWindow.warningBucket(3))
        assertEquals(1, BetaWindow.warningBucket(1))
        assertNull(BetaWindow.warningBucket(15))
        assertNull(BetaWindow.warningBucket(0))
    }
}
