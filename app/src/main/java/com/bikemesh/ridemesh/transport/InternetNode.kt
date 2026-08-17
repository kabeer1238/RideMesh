package com.bikemesh.ridemesh.transport

import com.hivemq.client.mqtt.MqttClient
import com.hivemq.client.mqtt.mqtt3.Mqtt3AsyncClient
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Experimental Internet transport for field testing.
 *
 * Uses HiveMQ's public TLS broker so distant RideMesh phones can test the
 * automatic Internet path before we deploy our own authenticated relay.
 * The public broker is test infrastructure only and must not be used as the
 * production RideMesh service.
 */
class InternetNode(private val listener: Listener) {
    interface Listener {
        fun onInternetState(connected: Boolean, message: String)
        fun onInternetAudio(audio: ByteArray)
    }

    private val nodeId = UUID.randomUUID()
    private val sequence = AtomicInteger(0)
    private val connected = AtomicBoolean(false)

    @Volatile private var client: Mqtt3AsyncClient? = null
    @Volatile private var topic: String? = null

    fun start(rideCode: String) {
        stop()
        val safeRide = rideCode.trim().uppercase().ifBlank { "RIDE01" }
            .replace(Regex("[^A-Z0-9_-]"), "_")
            .take(32)
        val rideTopic = "ridemesh/test/v1/$safeRide/audio"
        topic = rideTopic

        try {
            val mqtt = MqttClient.builder()
                .useMqttVersion3()
                .identifier("rm-${nodeId.toString().replace("-", "").take(20)}")
                .serverHost(PUBLIC_BROKER)
                .serverPort(PUBLIC_BROKER_TLS_PORT)
                .sslWithDefaultConfig()
                .automaticReconnectWithDefaultConfig()
                .addConnectedListener {
                    connected.set(true)
                    listener.onInternetState(true, "Internet relay connected")
                }
                .addDisconnectedListener {
                    connected.set(false)
                    listener.onInternetState(false, "Internet relay unavailable • using local mesh")
                }
                .buildAsync()

            client = mqtt
            listener.onInternetState(false, "Internet relay connecting…")

            mqtt.connect().whenComplete { _, error ->
                if (error != null) {
                    connected.set(false)
                    listener.onInternetState(false, "Internet relay unavailable • using local mesh")
                    return@whenComplete
                }

                mqtt.subscribeWith()
                    .topicFilter(rideTopic)
                    .callback { publish ->
                        val bytes = publish.payloadAsBytes
                        val packet = decode(bytes) ?: return@callback
                        if (packet.origin == nodeId) return@callback
                        listener.onInternetAudio(packet.audio)
                    }
                    .send()
                    .whenComplete { _, subscribeError ->
                        if (subscribeError != null) {
                            connected.set(false)
                            listener.onInternetState(false, "Internet subscription failed • using local mesh")
                        } else {
                            connected.set(true)
                            listener.onInternetState(true, "Internet relay active")
                        }
                    }
            }
        } catch (_: Throwable) {
            connected.set(false)
            listener.onInternetState(false, "Internet relay unavailable • using local mesh")
        }
    }

    fun isConnected(): Boolean = connected.get()

    fun sendLocalAudio(audio: ByteArray): Boolean {
        if (audio.isEmpty() || !connected.get()) return false
        val mqtt = client ?: return false
        val rideTopic = topic ?: return false
        val packet = encode(
            InternetPacket(
                origin = nodeId,
                sequence = sequence.incrementAndGet(),
                timestampMs = System.currentTimeMillis(),
                audio = audio,
            )
        )

        return try {
            mqtt.publishWith()
                .topic(rideTopic)
                .payload(packet)
                .send()
                .whenComplete { _, error ->
                    if (error != null) {
                        connected.set(false)
                        listener.onInternetState(false, "Internet send failed • using local mesh")
                    }
                }
            true
        } catch (_: Throwable) {
            connected.set(false)
            listener.onInternetState(false, "Internet send failed • using local mesh")
            false
        }
    }

    fun stop() {
        connected.set(false)
        val mqtt = client
        client = null
        topic = null
        if (mqtt != null) {
            try { mqtt.disconnect() } catch (_: Throwable) {}
        }
    }

    private data class InternetPacket(
        val origin: UUID,
        val sequence: Int,
        val timestampMs: Long,
        val audio: ByteArray,
    )

    private fun encode(packet: InternetPacket): ByteArray {
        val buffer = ByteBuffer.allocate(HEADER_BYTES + packet.audio.size).order(ByteOrder.BIG_ENDIAN)
        buffer.putInt(MAGIC)
        buffer.put(VERSION)
        buffer.putLong(packet.origin.mostSignificantBits)
        buffer.putLong(packet.origin.leastSignificantBits)
        buffer.putInt(packet.sequence)
        buffer.putLong(packet.timestampMs)
        buffer.put(packet.audio)
        return buffer.array()
    }

    private fun decode(bytes: ByteArray): InternetPacket? {
        if (bytes.size < HEADER_BYTES) return null
        return try {
            val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
            if (buffer.int != MAGIC) return null
            if (buffer.get() != VERSION) return null
            val origin = UUID(buffer.long, buffer.long)
            val sequence = buffer.int
            val timestamp = buffer.long
            val audio = ByteArray(buffer.remaining())
            buffer.get(audio)
            InternetPacket(origin, sequence, timestamp, audio)
        } catch (_: Throwable) {
            null
        }
    }

    companion object {
        private const val PUBLIC_BROKER = "broker.hivemq.com"
        private const val PUBLIC_BROKER_TLS_PORT = 8883
        private const val MAGIC = 0x524D4931 // RMI1
        private const val VERSION: Byte = 1
        private const val HEADER_BYTES = 37
    }
}
