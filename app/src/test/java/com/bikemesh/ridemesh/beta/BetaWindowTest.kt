package com.bikemesh.ridemesh.beta

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Test

class BetaWindowTest {
    private val start = 1_700_000_000_000L

    @Test fun productionNeverExpiresAtLegacyDeadline() {
        val legacyExpiry = start + BetaWindow.DURATION_MS
        assertFalse(BetaWindow.isExpired(start, legacyExpiry))
        assertFalse(BetaWindow.isExpired(start, Long.MAX_VALUE))
    }

    @Test fun productionDoesNotShowExpiryWarnings() {
        assertNull(BetaWindow.warningBucket(14))
        assertNull(BetaWindow.warningBucket(7))
        assertNull(BetaWindow.warningBucket(1))
        assertNull(BetaWindow.warningBucket(0))
    }

    @Test fun compatibilityCountdownCannotReachZero() {
        assertEquals(60L, BetaWindow.remainingDays(start, start))
        assertEquals(60L, BetaWindow.remainingDays(start, start + 365L * BetaWindow.DAY_MS))
    }
}
