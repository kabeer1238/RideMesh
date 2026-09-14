package com.bikemesh.ridemesh.transport

import org.junit.Assert.*
import org.junit.Test

class AutoTransportPolicyTest {
    @Test fun outageAndStableRecovery() {
        val policy = AutoTransportPolicy()
        assertTrue(policy.reset(true, 0))
        assertTrue(policy.update(false, 100))
        assertTrue(policy.update(false, 2099))
        assertFalse(policy.update(false, 2100))
        assertFalse(policy.update(true, 3000))
        assertFalse(policy.update(true, 10999))
        assertTrue(policy.update(true, 11000))
    }
    @Test fun intermittentCoverageDoesNotOscillate() {
        val policy = AutoTransportPolicy()
        policy.reset(false, 0)
        for (i in 1..30) {
            assertFalse(policy.update(true, i * 10000L))
            assertFalse(policy.update(false, i * 10000L + 7000))
        }
        assertFalse(policy.update(true, 400000))
        assertTrue(policy.update(true, 408000))
        assertTrue(policy.update(false, 409000))
        assertTrue(policy.update(true, 410000))
    }
    @Test fun freshRideDiscardsPreviousCandidate() {
        val policy = AutoTransportPolicy()
        policy.reset(false, 0)
        policy.update(true, 100)
        assertFalse(policy.reset(false, 20000))
        assertFalse(policy.update(true, 20001))
        assertFalse(policy.update(true, 21000))
    }
}
