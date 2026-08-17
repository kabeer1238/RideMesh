package com.bikemesh.ridemesh.transport

import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.EOFException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import javax.net.ssl.SSLSocket
import javax.net.ssl.SSLSocketFactory

/**
 * Experimental Internet transport for field testing.
 *
 * This deliberately implements only the small MQTT 3.1.1 subset RideMesh
 * needs (CONNECT, SUBSCRIBE, QoS-0 PUBLISH, PING). It avoids pulling a large
 * networking stack into the Android APK. The public broker remains TEST-ONLY.
 */
class InternetNode(private val listener: Listener) {
    interface Listener {
        fun onInternetState(connected: Boolean, message: String)
        fun onInternetAudio(audio: ByteArray)
    }

    private val nodeId = UUID.randomUUID()
    private val sequence = AtomicInteger(0)
    private val connected = AtomicBoolean(false)
    private val running = AtomicBoolean(false)
    private val outputLock = Any()

    @Volatile private var topic: String = ""
    @Volatile private var socket: SSLSocket? = null
    @Volatile private var output: BufferedOutputStream? = null
    @Volatile private var worker: Thread? = null

    fun start(rideCode: String) {
        stop()
        val safeRide = rideCode.trim().uppercase().ifBlank { "RIDE01" }
            .replace(Regex("[^A-Z0-9_-]"), "_")
            .take(32)
        topic = "ridemesh/test/v1/$safeRide/audio"
        running.set(true)
        listener.onInternetState(false, "Internet relay connecting…")

        worker = Thread({ connectionLoop() }, "RideMesh-Internet").apply {
            isDaemon = true
            start()
        }
    }

    fun isConnected(): Boolean = connected.get()

    fun sendLocalAudio(audio: ByteArray): Boolean {
        if (audio.isEmpty() || !connected.get()) return false
        val packet = encode(
            InternetPacket(
                origin = nodeId,
                sequence = sequence.incrementAndGet(),
                timestampMs = System.currentTimeMillis(),
                audio = audio,
            )
        )
        return try {
            sendMqttPublish(topic, packet)
            true
        } catch (_: Throwable) {
            markDisconnected("Internet send failed • using local mesh")
            closeSocket()
            false
        }
    }

    fun stop() {
        running.set(false)
        connected.set(false)
        closeSocket()
        worker?.interrupt()
        worker = null
    }

    private fun connectionLoop() {
        while (running.get()) {
            try {
                connectAndRead()
            } catch (_: InterruptedException) {
                break
            } catch (_: Throwable) {
                if (running.get()) markDisconnected("Internet relay unavailable • using local mesh")
            } finally {
                closeSocket()
            }

            if (running.get()) {
                try { Thread.sleep(RECONNECT_DELAY_MS) } catch (_: InterruptedException) { break }
                listener.onInternetState(false, "Internet relay reconnecting… • local mesh available")
            }
        }
    }

    private fun connectAndRead() {
        val tls = (SSLSocketFactory.getDefault().createSocket(PUBLIC_BROKER, PUBLIC_BROKER_TLS_PORT) as SSLSocket).apply {
            soTimeout = SOCKET_TIMEOUT_MS
            startHandshake()
        }
        socket = tls
        val input = BufferedInputStream(tls.inputStream)
        val out = BufferedOutputStream(tls.outputStream)
        output = out

        sendRaw(connectPacket())
        val connAck = readPacket(input)
        if (connAck.type != 2 || connAck.body.size < 2 || connAck.body[1].toInt() != 0) {
            throw IllegalStateException("MQTT broker rejected connection")
        }

        sendRaw(subscribePacket(topic))
        connected.set(true)
        listener.onInternetState(true, "Internet relay active")

        var lastPing = System.currentTimeMillis()
        while (running.get() && !tls.isClosed) {
            try {
                val mqtt = readPacket(input)
                if (mqtt.type == 3) handlePublish(mqtt.body)
            } catch (_: java.net.SocketTimeoutException) {
                // Timeout is also our keep-alive timer; the socket remains usable.
            }

            val now = System.currentTimeMillis()
            if (now - lastPing >= PING_INTERVAL_MS) {
                sendRaw(byteArrayOf(0xC0.toByte(), 0x00))
                lastPing = now
            }
        }
    }

    private fun handlePublish(body: ByteArray) {
        if (body.size < 2) return
        val topicLen = ((body[0].toInt() and 0xff) shl 8) or (body[1].toInt() and 0xff)
        if (topicLen <= 0 || body.size < 2 + topicLen) return
        val receivedTopic = body.copyOfRange(2, 2 + topicLen).toString(Charsets.UTF_8)
        if (receivedTopic != topic) return
        val payload = body.copyOfRange(2 + topicLen, body.size)
        val packet = decode(payload) ?: return
        if (packet.origin == nodeId) return
        listener.onInternetAudio(packet.audio)
    }

    private fun sendMqttPublish(topic: String, payload: ByteArray) {
        val topicBytes = topic.toByteArray(Charsets.UTF_8)
        val variable = ByteArrayOutputStream().apply {
            writeUtf8(topicBytes)
            write(payload)
        }.toByteArray()
        sendRaw(fixedPacket(0x30, variable)) // PUBLISH, QoS 0
    }

    private fun connectPacket(): ByteArray {
        val clientId = "rm-${nodeId.toString().replace("-", "").take(20)}".toByteArray(Charsets.UTF_8)
        val body = ByteArrayOutputStream().apply {
            writeUtf8("MQTT".toByteArray(Charsets.UTF_8))
            write(0x04) // MQTT 3.1.1
            write(0x02) // clean session
            write((KEEP_ALIVE_SECONDS shr 8) and 0xff)
            write(KEEP_ALIVE_SECONDS and 0xff)
            writeUtf8(clientId)
        }.toByteArray()
        return fixedPacket(0x10, body)
    }

    private fun subscribePacket(topic: String): ByteArray {
        val topicBytes = topic.toByteArray(Charsets.UTF_8)
        val body = ByteArrayOutputStream().apply {
            write(0x00)
            write(0x01) // packet id 1
            writeUtf8(topicBytes)
            write(0x00) // QoS 0
        }.toByteArray()
        return fixedPacket(0x82, body)
    }

    private fun sendRaw(packet: ByteArray) {
        val out = output ?: throw IllegalStateException("Internet relay not connected")
        synchronized(outputLock) {
            out.write(packet)
            out.flush()
        }
    }

    private data class MqttPacket(val type: Int, val body: ByteArray)

    private fun readPacket(input: BufferedInputStream): MqttPacket {
        val first = input.read()
        if (first < 0) throw EOFException()
        val remaining = readRemainingLength(input)
        val body = ByteArray(remaining)
        DataInputStream(input).readFully(body)
        return MqttPacket((first ushr 4) and 0x0f, body)
    }

    private fun readRemainingLength(input: BufferedInputStream): Int {
        var multiplier = 1
        var value = 0
        var loops = 0
        while (true) {
            val digit = input.read()
            if (digit < 0) throw EOFException()
            value += (digit and 127) * multiplier
            if ((digit and 128) == 0) return value
            multiplier *= 128
            loops++
            if (loops >= 4) throw IllegalStateException("Malformed MQTT remaining length")
        }
    }

    private fun fixedPacket(header: Int, body: ByteArray): ByteArray {
        val remaining = encodeRemainingLength(body.size)
        return ByteArray(1 + remaining.size + body.size).also { packet ->
            packet[0] = header.toByte()
            remaining.copyInto(packet, 1)
            body.copyInto(packet, 1 + remaining.size)
        }
    }

    private fun encodeRemainingLength(length: Int): ByteArray {
        var x = length
        val out = ByteArrayOutputStream(4)
        do {
            var digit = x % 128
            x /= 128
            if (x > 0) digit = digit or 0x80
            out.write(digit)
        } while (x > 0)
        return out.toByteArray()
    }

    private fun ByteArrayOutputStream.writeUtf8(bytes: ByteArray) {
        write((bytes.size shr 8) and 0xff)
        write(bytes.size and 0xff)
        write(bytes)
    }

    private fun markDisconnected(message: String) {
        val wasConnected = connected.getAndSet(false)
        if (wasConnected || running.get()) listener.onInternetState(false, message)
    }

    private fun closeSocket() {
        connected.set(false)
        synchronized(outputLock) {
            try { output?.close() } catch (_: Throwable) {}
            output = null
            try { socket?.close() } catch (_: Throwable) {}
            socket = null
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
        private const val KEEP_ALIVE_SECONDS = 30
        private const val SOCKET_TIMEOUT_MS = 10_000
        private const val PING_INTERVAL_MS = 15_000L
        private const val RECONNECT_DELAY_MS = 2_000L
        private const val MAGIC = 0x524D4931 // RMI1
        private const val VERSION: Byte = 1
        private const val HEADER_BYTES = 37
    }
}
