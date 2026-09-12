package com.bikemesh.ridemesh.offline

/** Destination-specific gateway leases. Only local-path presence may nominate a gateway.
 * A gateway must have an OPEN data channel to the destination, not just internet signaling.
 * Local monotonic expiry also works when phones' wall clocks disagree.
 */
class GatewayElection(private val localId: String, private val clock: () -> Long) {
    private data class Lease(val destinations: Set<String>, val at: Long)
    private val leases = mutableMapOf<String, Lease>()
    @Synchronized fun observe(gateway: String, destinations: Set<String>) {
        if (gateway == localId) return
        if (leases.size >= 7 && gateway !in leases) return
        leases[gateway] = Lease(destinations.take(7).toSet(), clock())
    }
    @Synchronized fun selected(destination: String): String {
        val now = clock()
        leases.entries.removeAll { now - it.value.at >= 6000 }
        return (leases.filterValues { destination in it.destinations }.keys + localId).minOrNull()!!
    }
}
