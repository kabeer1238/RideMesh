package com.bikemesh.ridemesh.offline

import org.junit.Assert.*
import org.junit.Test
import java.util.UUID
import java.util.ArrayDeque

class HybridMeshTest {
    private class Group {
        val ids = List(8) { UUID(0, (it + 1).toLong()) }
        var now = 0L
        val online = mutableSetOf(0, 1, 2, 3, 4)
        // Three offline riders behind online riders 0 and 1. Riders 2–4 have no local link.
        val local = mutableSetOf(0 to 5, 1 to 5, 5 to 6, 6 to 7)
        val elections = ids.map { GatewayElection(it.toString()) { now } }
        val played = IntArray(8)
        var internetTransfers = 0
        data class Delivery(val from: Int, val to: Int, val bytes: ByteArray, val internet: Boolean)
        val queue = ArrayDeque<Delivery>()
        fun links(a: Int, b: Int) = (a to b) in local || (b to a) in local
        val routers = ids.mapIndexed { i, id ->
            MeshRelayRouter(id, { exclude, bytes ->
                var sent = false
                for (j in ids.indices) if (links(i, j) && ids[j].toString() != exclude) {
                    queue.add(Delivery(i, j, bytes, false)); sent = true
                }
                sent
            }, { if (it.type == RideMeshEnvelope.Type.AUDIO) played[i]++ }, {}, { packet ->
                var sent = false
                if (i in online) for (j in online) {
                    if (j == i || ids[j] == packet.originNodeId) continue
                    if (packet.originNodeId == id || elections[i].selected(ids[j].toString()) == id.toString()) {
                        assertEquals(1, packet.internetHops)
                        queue.add(Delivery(i, j, packet.encode(), true)); internetTransfers++; sent = true
                    }
                }
                sent
            })
        }
        fun advertise() {
            // The controller derives these leases from local-path presence only.
            for (i in listOf(0,1,5,6,7)) for (j in listOf(0,1)) if (i != j) {
                elections[i].observe(ids[j].toString(), if (j in online)
                    online.filter { it != j }.map { ids[it].toString() }.toSet() else emptySet())
            }
        }
        fun speak(source: Int) {
            played.fill(0); internetTransfers = 0
            routers[source].originateAudio(byteArrayOf(1,2,3))
            var steps = 0
            while (queue.isNotEmpty()) {
                assertTrue("Flood must terminate", ++steps < 300)
                val d = queue.removeFirst()
                if (d.internet && (d.from !in online || d.to !in online)) continue
                routers[d.to].receive(ids[d.from].toString(), d.bytes)
            }
            ids.indices.forEach { assertEquals("source $source receiver $it", if (it == source) 0 else 1, played[it]) }
        }
    }
    @Test fun fiveOnlineThreeOfflineAllEightCanSpeakWithoutDuplicatePlayout() {
        val group = Group(); group.advertise()
        for (source in 0..7) group.speak(source)
    }
    @Test fun redundantGatewaysBeforeElectionStillTerminateAndPlayOnce() {
        val group = Group()
        for (source in 0..7) group.speak(source)
    }
    @Test fun electedGatewayInternetLossAndLeaseExpiryRecoverViaBackup() {
        val group = Group(); group.advertise(); group.speak(7)
        group.online.remove(0)
        group.now = 6001 // Abrupt gateway failure; its old announcement expires.
        group.speak(7); group.speak(4)
        group.online.add(0); group.advertise(); group.speak(6)
    }
    @Test fun explicitGatewayWithdrawalAndDestinationSpecificElection() {
        var now = 0L
        val election = GatewayElection("b") { now }
        election.observe("a", setOf("x"))
        assertEquals("a", election.selected("x"))
        assertEquals("b", election.selected("y"))
        election.observe("a", emptySet())
        assertEquals("b", election.selected("x"))
        election.observe("a", setOf("x")); now = 6000
        assertEquals("b", election.selected("x"))
    }
    @Test fun internetIngressCannotBeUploadedAgainAndSpoofedPreviousHopIsRejected() {
        val a = UUID.randomUUID(); val b = UUID.randomUUID()
        var plays = 0; var uploads = 0
        val router = MeshRelayRouter(b, { _, _ -> true }, { plays++ }, {}, { uploads++; true })
        val frame = RideMeshEnvelope.newDiagnostic(a, 1, "probe").copy(internetHops = 1)
        router.receive(UUID.randomUUID().toString(), frame.encode())
        assertEquals(0, plays)
        router.receive(a.toString(), frame.encode()); router.receive(a.toString(), frame.encode())
        assertEquals(1, plays); assertEquals(0, uploads)
        val invalid = frame.encode(); invalid[6] = 2
        assertNull(RideMeshEnvelope.decode(invalid))
    }
    @Test fun channelCloseDefersDisposalUntilInFlightCallReturns() {
        val entered = java.util.concurrent.CountDownLatch(1)
        val finish = java.util.concurrent.CountDownLatch(1)
        val disposed = java.util.concurrent.atomic.AtomicInteger()
        val lease = ChannelLease("native") { disposed.incrementAndGet() }
        val worker = Thread {
            lease.use { entered.countDown(); finish.await(2, java.util.concurrent.TimeUnit.SECONDS) }
        }
        worker.start()
        assertTrue(entered.await(2, java.util.concurrent.TimeUnit.SECONDS))
        lease.close() // Must not block behind a call waiting on a native callback.
        assertEquals(0, disposed.get())
        assertNull(lease.use { it })
        finish.countDown(); worker.join(2000)
        assertFalse(worker.isAlive)
        lease.close()
        assertEquals(1, disposed.get())
    }
    @Test fun eightRiderPureLocalChainReachesSevenLinks() {
        val group = Group(); group.online.clear(); group.local.clear()
        for (i in 0..6) group.local.add(i to i+1)
        for (source in 0..7) group.speak(source)
    }
}
