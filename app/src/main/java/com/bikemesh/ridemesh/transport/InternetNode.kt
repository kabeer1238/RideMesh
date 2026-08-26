package com.bikemesh.ridemesh.transport

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Build
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.DataChannel
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.audio.JavaAudioDeviceModule
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.EOFException
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.random.Random
import javax.net.ssl.SSLSocket
import javax.net.ssl.SSLSocketFactory

/**
 * Beta4 Internet voice engine.
 *
 * MQTT/TLS is used only for room presence plus SDP/ICE signaling. Microphone audio is never
 * published through MQTT in Beta4. Voice is a WebRTC audio track, which negotiates Opus and uses
 * WebRTC NetEq jitter handling / packet-loss recovery over encrypted SRTP media.
 *
 * Each rider creates a direct PeerConnection to each other rider in the same ride code. This is a
 * practical 2-6 rider Beta architecture and removes all Nearby/offline/bridge timing from the
 * production voice path. STUN is included for NAT traversal. Production TURN credentials are not
 * hard-coded into this public Beta yet, so diagnostics explicitly report TURN as not configured.
 *
 * The old InternetPacket encode/decode helpers remain only for source/unit-test compatibility.
 */
class InternetNode(
    private val listener: Listener,
    private val context: Context? = null,
) {
    interface Listener {
        fun onInternetState(connected: Boolean, message: String)
        fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray)
        fun onInternetPeerCount(count: Int)
        fun onInternetAudioStatus(message: String) = Unit
    }

    data class RiderPeer(
        val id: UUID,
        val riderName: String,
        val deviceName: String,
        val lastSeenMs: Long,
        val qualityBars: Int = 4,
    ) {
        val displayName: String
            get() = riderName.ifBlank {
                deviceName.ifBlank { "Rider ${id.toString().take(4).uppercase()}" }
            }
    }

    data class Diagnostics(
        val signalingConnected: Boolean,
        val voicePeersConnected: Int,
        val knownRiders: Int,
        val offersSent: Int,
        val answersSent: Int,
        val candidatesSent: Int,
        val reconnects: Int,
        val lastError: String,
        val peerStates: String,
        val codec: String = "Opus / WebRTC",
        val turnConfigured: Boolean = false,
    )

    private data class PeerSession(
        val id: UUID,
        val pc: PeerConnection,
        val initiator: Boolean,
        val pendingCandidates: MutableList<IceCandidate> = CopyOnWriteArrayList(),
        @Volatile var remoteDescriptionSet: Boolean = false,
        @Volatile var connected: Boolean = false,
        @Volatile var state: String = "NEW",
        @Volatile var lastOfferMs: Long = 0L,
        @Volatile var lastStateChangeMs: Long = System.currentTimeMillis(),
        @Volatile var reconnectScheduled: Boolean = false,
    )

    private val appContext: Context?
        get() = context?.applicationContext

    private val nodeId: UUID by lazy {
        val ctx = appContext
        if (ctx == null) {
            UUID.randomUUID()
        } else {
            val prefs = ctx.getSharedPreferences("ridemesh", Context.MODE_PRIVATE)
            val saved = prefs.getString(WEBRTC_NODE_ID_KEY, null)
            runCatching { UUID.fromString(saved) }.getOrElse {
                UUID.randomUUID().also { generated ->
                    prefs.edit().putString(WEBRTC_NODE_ID_KEY, generated.toString()).apply()
                }
            }
        }
    }

    private val running = AtomicBoolean(false)
    private val signalingConnected = AtomicBoolean(false)
    private val reportedPeerCount = AtomicInteger(-1)
    private val offersSent = AtomicInteger(0)
    private val answersSent = AtomicInteger(0)
    private val candidatesSent = AtomicInteger(0)
    private val reconnects = AtomicInteger(0)

    private val peers = ConcurrentHashMap<UUID, RiderPeer>()
    private val sessions = ConcurrentHashMap<UUID, PeerSession>()
    private val outputLock = Any()

    @Volatile private var riderName: String = "Rider"
    @Volatile private var deviceName: String = "Android device"
    @Volatile private var baseTopic: String = ""
    @Volatile private var presenceTopic: String = ""
    @Volatile private var signalTopic: String = ""
    @Volatile private var subscriptionTopic: String = ""
    @Volatile private var socket: SSLSocket? = null
    @Volatile private var output: BufferedOutputStream? = null
    @Volatile private var worker: Thread? = null
    @Volatile private var lastError: String = ""
    @Volatile private var reconnectAttempt = 0
    @Volatile private var userMuted = false
    @Volatile private var focusPaused = false
    @Volatile private var audioRoute = "AUTO"
    @Volatile private var audioStatus = "WEBRTC AUDIO READY"

    private var factory: PeerConnectionFactory? = null
    private var audioSource: AudioSource? = null
    private var localAudioTrack: AudioTrack? = null
    private var audioDeviceModule: JavaAudioDeviceModule? = null
    private var audioManager: AudioManager? = null
    private var audioFocusRequest: AudioFocusRequest? = null

    fun start(rideCode: String, riderName: String, deviceName: String) {
        val ctx = appContext ?: throw IllegalStateException("Android context required for WebRTC voice")
        stop()

        this.riderName = sanitizeIdentity(riderName, "Rider", MAX_RIDER_NAME_BYTES)
        this.deviceName = sanitizeIdentity(deviceName, "Android device", MAX_DEVICE_NAME_BYTES)
        val safeRide = rideCode.trim().uppercase().ifBlank { "RIDE01" }
            .replace(Regex("[^A-Z0-9_-]"), "_")
            .take(32)

        baseTopic = "ridemesh/test/v3/$safeRide"
        presenceTopic = "$baseTopic/presence"
        signalTopic = "$baseTopic/signal"
        subscriptionTopic = "$baseTopic/#"

        lastError = ""
        reconnectAttempt = 0
        offersSent.set(0)
        answersSent.set(0)
        candidatesSent.set(0)
        reconnects.set(0)

        initializeWebRtc(ctx)
        running.set(true)
        requestAudioFocus()
        selectAudioRoute()
        applyVoiceEnabled()

        listener.onInternetState(false, "WEBRTC SIGNALING CONNECTING • OPUS VOICE")
        worker = Thread({ connectionLoop() }, "RideMesh-WebRTC-Signaling").apply {
            isDaemon = true
            start()
        }
    }

    fun stop() {
        val wasRunning = running.getAndSet(false)
        if (wasRunning && signalingConnected.get()) {
            runCatching { publishSignal(SignalPacket(nodeId, BROADCAST_ID, SignalType.BYE)) }
        }

        signalingConnected.set(false)
        closeSocket()
        worker?.interrupt()
        worker = null

        closeAllPeerConnections()
        peers.clear()
        notifyPeerCount(force = true)

        localAudioTrack?.setEnabled(false)
        runCatching { localAudioTrack?.dispose() }
        localAudioTrack = null
        runCatching { audioSource?.dispose() }
        audioSource = null
        runCatching { factory?.dispose() }
        factory = null
        runCatching { audioDeviceModule?.release() }
        audioDeviceModule = null

        abandonAudioFocus()
        clearCommunicationRoute()
    }

    fun isConnected(): Boolean = signalingConnected.get() || voicePeerCount() > 0

    fun remotePeerCount(): Int = peers.size

    fun voicePeerCount(): Int = sessions.values.count { it.connected }

    fun remotePeers(): List<RiderPeer> = peers.values
        .map { peer -> peer.copy(qualityBars = qualityBarsFor(peer.id)) }
        .sortedWith(compareBy(String.CASE_INSENSITIVE_ORDER) { it.displayName })

    /**
     * Legacy API only. Beta4 WebRTC captures the microphone directly; raw PCM is never sent over
     * the signaling broker.
     */
    fun sendLocalAudio(audio: ByteArray): Boolean = false

    fun setMuted(muted: Boolean) {
        userMuted = muted
        applyVoiceEnabled()
        audioStatus = if (muted) {
            "MIC MUTED • LISTENING ONLY"
        } else if (focusPaused) {
            "CALL / OTHER AUDIO ACTIVE • RIDEMESH PAUSED"
        } else {
            "WEBRTC OPUS • MIC LIVE"
        }
        listener.onInternetAudioStatus(audioStatus)
    }

    fun setAudioRoute(route: String): String {
        audioRoute = route.uppercase()
        val result = selectAudioRoute()
        listener.onInternetAudioStatus(result)
        return result
    }

    fun currentAudioStatus(): String = audioStatus

    fun diagnostics(): Diagnostics {
        val stateText = sessions.values
            .sortedBy { it.id.toString() }
            .joinToString(separator = "\n") { session ->
                "${session.id.toString().take(8)}: ${session.state}${if (session.connected) " • VOICE" else ""}"
            }
            .ifBlank { "No WebRTC peers yet" }
        return Diagnostics(
            signalingConnected = signalingConnected.get(),
            voicePeersConnected = voicePeerCount(),
            knownRiders = peers.size,
            offersSent = offersSent.get(),
            answersSent = answersSent.get(),
            candidatesSent = candidatesSent.get(),
            reconnects = reconnects.get(),
            lastError = lastError,
            peerStates = stateText,
        )
    }

    private fun initializeWebRtc(ctx: Context) {
        if (factory != null) return

        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(ctx)
                .setEnableInternalTracer(false)
                .createInitializationOptions()
        )

        val voiceAttributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()

        val adm = JavaAudioDeviceModule.builder(ctx)
            .setUseHardwareAcousticEchoCanceler(
                JavaAudioDeviceModule.isBuiltInAcousticEchoCancelerSupported()
            )
            .setUseHardwareNoiseSuppressor(
                JavaAudioDeviceModule.isBuiltInNoiseSuppressorSupported()
            )
            .setUseStereoInput(false)
            .setUseStereoOutput(false)
            .setUseLowLatency(true)
            .setAudioAttributes(voiceAttributes)
            .createAudioDeviceModule()

        audioDeviceModule = adm
        factory = PeerConnectionFactory.builder()
            .setAudioDeviceModule(adm)
            .createPeerConnectionFactory()

        val constraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("googEchoCancellation", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googNoiseSuppression", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googAutoGainControl", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("googHighpassFilter", "true"))
        }
        audioSource = factory?.createAudioSource(constraints)
        localAudioTrack = audioSource?.let { source ->
            factory?.createAudioTrack(LOCAL_AUDIO_TRACK_ID, source)
        }
        audioManager = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioStatus = "WEBRTC OPUS • AEC + NS • READY"
        listener.onInternetAudioStatus(audioStatus)
    }

    private fun ensurePeer(peerId: UUID, allowOffer: Boolean = true): PeerSession? {
        sessions[peerId]?.let { existing ->
            if (allowOffer && existing.initiator && !existing.connected) maybeCreateOffer(existing)
            return existing
        }

        val factory = factory ?: return null
        val localTrack = localAudioTrack ?: return null
        val initiator = nodeId.toString() < peerId.toString()

        val config = PeerConnection.RTCConfiguration(
            listOf(
                PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer(),
                PeerConnection.IceServer.builder("stun:stun1.l.google.com:19302").createIceServer(),
            )
        ).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            bundlePolicy = PeerConnection.BundlePolicy.MAXBUNDLE
            rtcpMuxPolicy = PeerConnection.RtcpMuxPolicy.REQUIRE
            iceTransportsType = PeerConnection.IceTransportsType.ALL
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
            audioJitterBufferMaxPackets = 50
            audioJitterBufferFastAccelerate = true
            iceCandidatePoolSize = 2
        }

        val observer = object : PeerConnection.Observer {
            override fun onSignalingChange(newState: PeerConnection.SignalingState) {
                updatePeerState(peerId, "SDP $newState")
            }

            override fun onIceConnectionChange(newState: PeerConnection.IceConnectionState) {
                when (newState) {
                    PeerConnection.IceConnectionState.CONNECTED,
                    PeerConnection.IceConnectionState.COMPLETED ->
                        markPeerConnected(peerId, true, "ICE $newState")

                    PeerConnection.IceConnectionState.FAILED -> {
                        markPeerConnected(peerId, false, "ICE FAILED")
                        schedulePeerReconnect(peerId, immediate = true)
                    }

                    PeerConnection.IceConnectionState.DISCONNECTED -> {
                        markPeerConnected(peerId, false, "ICE DISCONNECTED")
                        schedulePeerReconnect(peerId, immediate = false)
                    }

                    PeerConnection.IceConnectionState.CLOSED ->
                        markPeerConnected(peerId, false, "ICE CLOSED")

                    else -> updatePeerState(peerId, "ICE $newState")
                }
            }

            override fun onConnectionChange(newState: PeerConnection.PeerConnectionState) {
                when (newState) {
                    PeerConnection.PeerConnectionState.CONNECTED ->
                        markPeerConnected(peerId, true, "CONNECTED")

                    PeerConnection.PeerConnectionState.FAILED -> {
                        markPeerConnected(peerId, false, "FAILED")
                        schedulePeerReconnect(peerId, immediate = true)
                    }

                    PeerConnection.PeerConnectionState.DISCONNECTED -> {
                        markPeerConnected(peerId, false, "DISCONNECTED")
                        schedulePeerReconnect(peerId, immediate = false)
                    }

                    PeerConnection.PeerConnectionState.CLOSED ->
                        markPeerConnected(peerId, false, "CLOSED")

                    else -> updatePeerState(peerId, newState.name)
                }
            }

            override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit

            override fun onIceGatheringChange(newState: PeerConnection.IceGatheringState) {
                updatePeerState(peerId, "ICE GATHER $newState")
            }

            override fun onIceCandidate(candidate: IceCandidate) {
                if (!running.get()) return
                publishSignal(
                    SignalPacket(
                        from = nodeId,
                        to = peerId,
                        type = SignalType.CANDIDATE,
                        payload = candidate.sdp,
                        mid = candidate.sdpMid.orEmpty(),
                        line = candidate.sdpMLineIndex,
                    )
                )
                candidatesSent.incrementAndGet()
            }

            override fun onIceCandidatesRemoved(candidates: Array<IceCandidate>) = Unit
            override fun onAddStream(stream: MediaStream) = Unit
            override fun onRemoveStream(stream: MediaStream) = Unit
            override fun onDataChannel(dataChannel: DataChannel) = Unit

            override fun onRenegotiationNeeded() {
                sessions[peerId]?.let { session ->
                    if (session.initiator) maybeCreateOffer(session)
                }
            }

            override fun onAddTrack(receiver: RtpReceiver, mediaStreams: Array<MediaStream>) {
                receiver.track()?.setEnabled(true)
            }
        }

        val pc = factory.createPeerConnection(config, observer) ?: run {
            lastError = "Could not create WebRTC PeerConnection"
            listener.onInternetState(isConnected(), lastError)
            return null
        }

        val session = PeerSession(peerId, pc, initiator)
        sessions[peerId] = session
        pc.addTrack(localTrack, listOf(MEDIA_STREAM_ID))
        runCatching { pc.setBitrate(24_000, 40_000, 64_000) }
        updatePeerState(peerId, if (initiator) "READY TO OFFER" else "WAITING OFFER")

        if (allowOffer && initiator) maybeCreateOffer(session)
        return session
    }

    private fun maybeCreateOffer(session: PeerSession, force: Boolean = false) {
        if (!running.get() || !session.initiator || session.connected) return
        val now = System.currentTimeMillis()
        if (!force && now - session.lastOfferMs < OFFER_RETRY_INTERVAL_MS) return
        session.lastOfferMs = now

        if (!force && session.pc.signalingState() == PeerConnection.SignalingState.HAVE_LOCAL_OFFER) {
            session.pc.localDescription?.let { current ->
                publishSignal(
                    SignalPacket(nodeId, session.id, SignalType.OFFER, preferOpus(current.description))
                )
                offersSent.incrementAndGet()
                updatePeerState(session.id, "OFFER RETRANSMITTED")
                return
            }
        }

        val constraints = MediaConstraints().apply {
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "false"))
            if (force) mandatory.add(MediaConstraints.KeyValuePair("IceRestart", "true"))
        }

        session.pc.createOffer(object : SimpleSdpObserver() {
            override fun onCreateSuccess(desc: SessionDescription) {
                val preferred = SessionDescription(desc.type, preferOpus(desc.description))
                session.pc.setLocalDescription(object : SimpleSdpObserver() {
                    override fun onSetSuccess() {
                        publishSignal(
                            SignalPacket(
                                from = nodeId,
                                to = session.id,
                                type = SignalType.OFFER,
                                payload = preferred.description,
                            )
                        )
                        offersSent.incrementAndGet()
                        updatePeerState(session.id, if (force) "ICE RESTART OFFER" else "OFFER SENT")
                    }

                    override fun onSetFailure(error: String) {
                        recordError("Set local offer failed: $error")
                    }
                }, preferred)
            }

            override fun onCreateFailure(error: String) {
                recordError("Create offer failed: $error")
            }
        }, constraints)
    }

    private fun handleOffer(signal: SignalPacket) {
        val session = ensurePeer(signal.from, allowOffer = false) ?: return
        val remote = SessionDescription(SessionDescription.Type.OFFER, preferOpus(signal.payload))
        session.pc.setRemoteDescription(object : SimpleSdpObserver() {
            override fun onSetSuccess() {
                session.remoteDescriptionSet = true
                flushPendingCandidates(session)
                val constraints = MediaConstraints().apply {
                    mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
                    mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "false"))
                }
                session.pc.createAnswer(object : SimpleSdpObserver() {
                    override fun onCreateSuccess(desc: SessionDescription) {
                        val preferred = SessionDescription(desc.type, preferOpus(desc.description))
                        session.pc.setLocalDescription(object : SimpleSdpObserver() {
                            override fun onSetSuccess() {
                                publishSignal(
                                    SignalPacket(
                                        from = nodeId,
                                        to = signal.from,
                                        type = SignalType.ANSWER,
                                        payload = preferred.description,
                                    )
                                )
                                answersSent.incrementAndGet()
                                updatePeerState(signal.from, "ANSWER SENT")
                            }

                            override fun onSetFailure(error: String) {
                                recordError("Set local answer failed: $error")
                            }
                        }, preferred)
                    }

                    override fun onCreateFailure(error: String) {
                        recordError("Create answer failed: $error")
                    }
                }, constraints)
            }

            override fun onSetFailure(error: String) {
                recordError("Set remote offer failed: $error")
            }
        }, remote)
    }

    private fun handleAnswer(signal: SignalPacket) {
        val session = sessions[signal.from] ?: ensurePeer(signal.from, allowOffer = false) ?: return
        val remote = SessionDescription(SessionDescription.Type.ANSWER, preferOpus(signal.payload))
        session.pc.setRemoteDescription(object : SimpleSdpObserver() {
            override fun onSetSuccess() {
                session.remoteDescriptionSet = true
                flushPendingCandidates(session)
                updatePeerState(signal.from, "ANSWER APPLIED")
            }

            override fun onSetFailure(error: String) {
                recordError("Set remote answer failed: $error")
            }
        }, remote)
    }

    private fun handleCandidate(signal: SignalPacket) {
        val session = sessions[signal.from] ?: ensurePeer(signal.from, allowOffer = false) ?: return
        val candidate = IceCandidate(signal.mid.takeIf { it.isNotBlank() }, signal.line, signal.payload)
        if (session.remoteDescriptionSet || session.pc.remoteDescription != null) {
            session.pc.addIceCandidate(candidate)
        } else {
            session.pendingCandidates += candidate
        }
    }

    private fun flushPendingCandidates(session: PeerSession) {
        if (!session.remoteDescriptionSet && session.pc.remoteDescription == null) return
        val pending = session.pendingCandidates.toList()
        session.pendingCandidates.clear()
        pending.forEach { candidate -> session.pc.addIceCandidate(candidate) }
    }

    private fun schedulePeerReconnect(peerId: UUID, immediate: Boolean) {
        val session = sessions[peerId] ?: return
        if (session.reconnectScheduled || !running.get()) return
        session.reconnectScheduled = true
        Thread({
            try {
                Thread.sleep(if (immediate) ICE_FAILED_RETRY_MS else ICE_DISCONNECTED_GRACE_MS)
            } catch (_: InterruptedException) {
                return@Thread
            }

            val current = sessions[peerId] ?: return@Thread
            current.reconnectScheduled = false
            if (!running.get() || current.connected) return@Thread

            reconnects.incrementAndGet()
            if (current.initiator) {
                runCatching { current.pc.restartIce() }
                maybeCreateOffer(current, force = true)
            } else {
                updatePeerState(peerId, "WAITING ICE RESTART")
            }
        }, "RideMesh-ICE-Reconnect").apply {
            isDaemon = true
            start()
        }
    }

    private fun markPeerConnected(peerId: UUID, connected: Boolean, state: String) {
        val session = sessions[peerId] ?: return
        session.connected = connected
        session.state = state
        session.lastStateChangeMs = System.currentTimeMillis()
        peers.computeIfPresent(peerId) { _, peer ->
            peer.copy(qualityBars = qualityBarsFor(peerId))
        }
        notifyPeerCount(force = true)
        listener.onInternetState(
            isConnected(),
            if (connected) {
                val count = voicePeerCount()
                "WEBRTC OPUS VOICE CONNECTED • $count PEER${if (count == 1) "" else "S"}"
            } else {
                "WEBRTC $state • AUTO RECONNECT"
            }
        )
    }

    private fun updatePeerState(peerId: UUID, state: String) {
        sessions[peerId]?.let {
            it.state = state
            it.lastStateChangeMs = System.currentTimeMillis()
        }
    }

    private fun closePeer(peerId: UUID, sendBye: Boolean = false) {
        val session = sessions.remove(peerId) ?: return
        if (sendBye && signalingConnected.get()) {
            publishSignal(SignalPacket(nodeId, peerId, SignalType.BYE))
        }
        runCatching { session.pc.close() }
        runCatching { session.pc.dispose() }
        notifyPeerCount(force = true)
    }

    private fun closeAllPeerConnections() {
        sessions.keys.toList().forEach { closePeer(it, sendBye = false) }
        sessions.clear()
    }

    private fun qualityBarsFor(id: UUID): Int {
        val session = sessions[id] ?: return 2
        return when {
            session.connected -> 4
            session.state.contains("CONNECT", ignoreCase = true) ||
                session.state.contains("CHECK", ignoreCase = true) -> 3
            session.state.contains("FAIL", ignoreCase = true) ||
                session.state.contains("DISCONNECT", ignoreCase = true) -> 1
            else -> 2
        }
    }

    private fun connectionLoop() {
        while (running.get()) {
            try {
                connectAndRead()
            } catch (_: InterruptedException) {
                break
            } catch (t: Throwable) {
                if (running.get()) {
                    recordError("Signaling: ${t.javaClass.simpleName}: ${t.message ?: "connection error"}")
                    listener.onInternetState(
                        voicePeerCount() > 0,
                        if (voicePeerCount() > 0) {
                            "VOICE STILL ACTIVE • SIGNALING RECONNECTING"
                        } else {
                            "WEBRTC SIGNALING RECONNECTING"
                        }
                    )
                }
            } finally {
                closeSocket()
            }

            if (running.get()) {
                val delayMs = nextReconnectDelayMs()
                try {
                    Thread.sleep(delayMs)
                } catch (_: InterruptedException) {
                    break
                }
            }
        }
    }

    private fun connectAndRead() {
        val tls = (SSLSocketFactory.getDefault()
            .createSocket(PUBLIC_BROKER, PUBLIC_BROKER_TLS_PORT) as SSLSocket).apply {
            soTimeout = SOCKET_TIMEOUT_MS
            tcpNoDelay = true
            startHandshake()
        }
        socket = tls
        val input = BufferedInputStream(tls.inputStream)
        output = BufferedOutputStream(tls.outputStream)

        sendRaw(connectPacket())
        val connAck = readPacket(input)
        if (connAck.type != 2 || connAck.body.size < 2 || connAck.body[1].toInt() != 0) {
            throw IllegalStateException("MQTT signaling broker rejected connection")
        }

        sendRaw(subscribePacket(subscriptionTopic))
        signalingConnected.set(true)
        reconnectAttempt = 0
        lastError = ""
        listener.onInternetState(true, "WEBRTC SIGNALING READY • OPUS VOICE")
        publishPresence()

        var lastPing = System.currentTimeMillis()
        var lastPresence = 0L

        while (running.get() && !tls.isClosed) {
            try {
                val mqtt = readPacket(input)
                if (mqtt.type == 3) handlePublish(mqtt.body)
            } catch (_: java.net.SocketTimeoutException) {
                // Wake for presence, peer negotiation and signaling keepalive.
            }

            val now = System.currentTimeMillis()
            if (now - lastPresence >= PRESENCE_INTERVAL_MS) {
                publishPresence()
                refreshPeerNegotiation(now)
                prunePeers(now)
                lastPresence = now
            }
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
        val payload = body.copyOfRange(2 + topicLen, body.size)

        when (receivedTopic) {
            presenceTopic -> handlePresence(payload)
            signalTopic -> decodeSignal(payload)?.let(::handleSignal)
        }
    }

    private fun publishPresence() {
        if (!signalingConnected.get()) return
        sendMqttPublish(
            presenceTopic,
            encodePresence(
                PresencePacket(
                    origin = nodeId,
                    timestampMs = System.currentTimeMillis(),
                    riderName = riderName,
                    deviceName = deviceName,
                )
            )
        )
    }

    private fun handlePresence(payload: ByteArray) {
        val presence = decodePresence(payload) ?: return
        if (presence.origin == nodeId) return

        val now = System.currentTimeMillis()
        val previous = peers[presence.origin]
        peers[presence.origin] = RiderPeer(
            id = presence.origin,
            riderName = presence.riderName.ifBlank { previous?.riderName.orEmpty() },
            deviceName = presence.deviceName.ifBlank { previous?.deviceName.orEmpty() },
            lastSeenMs = now,
            qualityBars = qualityBarsFor(presence.origin),
        )
        notifyPeerCount(force = previous == null)
        ensurePeer(presence.origin, allowOffer = true)
    }

    private fun refreshPeerNegotiation(now: Long) {
        peers.keys.forEach { peerId ->
            val session = sessions[peerId] ?: ensurePeer(peerId, allowOffer = true)
            if (session != null && session.initiator && !session.connected &&
                now - session.lastOfferMs >= OFFER_RETRY_INTERVAL_MS
            ) {
                maybeCreateOffer(session)
            }
        }
    }

    private fun prunePeers(now: Long) {
        val stale = peers.values.filter { now - it.lastSeenMs > PRESENCE_TIMEOUT_MS }
        stale.forEach { peer ->
            val session = sessions[peer.id]
            // Keep a healthy SRTP connection alive across a temporary MQTT heartbeat gap.
            if (session == null || !session.connected) {
                peers.remove(peer.id)
                closePeer(peer.id, sendBye = false)
            }
        }
        notifyPeerCount()
    }

    private fun handleSignal(signal: SignalPacket) {
        if (signal.from == nodeId) return
        if (signal.to != nodeId && signal.to != BROADCAST_ID) return

        when (signal.type) {
            SignalType.OFFER -> handleOffer(signal)
            SignalType.ANSWER -> handleAnswer(signal)
            SignalType.CANDIDATE -> handleCandidate(signal)
            SignalType.BYE -> {
                peers.remove(signal.from)
                closePeer(signal.from, sendBye = false)
            }
        }
    }

    private fun publishSignal(signal: SignalPacket) {
        if (!signalingConnected.get()) return
        runCatching { sendMqttPublish(signalTopic, encodeSignal(signal)) }
            .onFailure { recordError("Signal send: ${it.javaClass.simpleName}: ${it.message ?: "error"}") }
    }

    private fun notifyPeerCount(force: Boolean = false) {
        val count = peers.size
        val previous = reportedPeerCount.getAndSet(count)
        if (force || previous != count) listener.onInternetPeerCount(count)
    }

    @SuppressLint("MissingPermission")
    private fun selectAudioRoute(): String {
        val manager = audioManager ?: return "WEBRTC AUDIO READY"
        return try {
            manager.mode = AudioManager.MODE_IN_COMMUNICATION
            val result = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val available = manager.availableCommunicationDevices
                val helmet = available.firstOrNull { it.isVoiceBluetoothDevice() }
                val speaker = available.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
                val earpiece = available.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_EARPIECE }

                val chosen = when (audioRoute) {
                    "HELMET" -> helmet ?: speaker ?: earpiece
                    "PHONE" -> speaker ?: earpiece
                    else -> helmet ?: speaker ?: earpiece
                }

                if (chosen == null) {
                    "WEBRTC AUDIO • NO COMMUNICATION DEVICE"
                } else {
                    val ok = manager.setCommunicationDevice(chosen)
                    val label = chosen.voiceRouteLabel()
                    if (ok) "WEBRTC OPUS • $label" else "WEBRTC ROUTE FAILED • $label"
                }
            } else {
                @Suppress("DEPRECATION")
                val hasSco = manager.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                    .any { it.type == AudioDeviceInfo.TYPE_BLUETOOTH_SCO }
                val useBluetooth = when (audioRoute) {
                    "HELMET" -> hasSco
                    "PHONE" -> false
                    else -> hasSco
                }
                @Suppress("DEPRECATION")
                if (useBluetooth) {
                    manager.isSpeakerphoneOn = false
                    manager.startBluetoothSco()
                    manager.isBluetoothScoOn = true
                    "WEBRTC OPUS • BLUETOOTH HELMET"
                } else {
                    manager.stopBluetoothSco()
                    manager.isBluetoothScoOn = false
                    manager.isSpeakerphoneOn = true
                    "WEBRTC OPUS • PHONE AUDIO"
                }
            }
            audioStatus = result
            result
        } catch (t: Throwable) {
            val result = "WEBRTC AUDIO ROUTE ERROR • ${t.javaClass.simpleName}"
            audioStatus = result
            recordError(result)
            result
        }
    }

    private fun AudioDeviceInfo.isVoiceBluetoothDevice(): Boolean = when (type) {
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
        AudioDeviceInfo.TYPE_BLE_HEADSET,
        AudioDeviceInfo.TYPE_BLE_SPEAKER -> true
        else -> false
    }

    private fun AudioDeviceInfo.voiceRouteLabel(): String = when (type) {
        AudioDeviceInfo.TYPE_BLUETOOTH_SCO,
        AudioDeviceInfo.TYPE_BLE_HEADSET,
        AudioDeviceInfo.TYPE_BLE_SPEAKER -> "BLUETOOTH HELMET"
        AudioDeviceInfo.TYPE_BUILTIN_SPEAKER -> "PHONE SPEAKER"
        AudioDeviceInfo.TYPE_BUILTIN_EARPIECE -> "PHONE EARPIECE"
        else -> productName?.toString()?.uppercase()?.take(32) ?: "AUDIO DEVICE"
    }

    private fun requestAudioFocus() {
        val manager = audioManager ?: return
        val attributes = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()

        val focusListener = AudioManager.OnAudioFocusChangeListener { change ->
            when (change) {
                AudioManager.AUDIOFOCUS_GAIN -> resumeAfterExternalAudio()
                AudioManager.AUDIOFOCUS_LOSS,
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> pauseForExternalAudio()
            }
        }

        audioFocusRequest = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(attributes)
            .setAcceptsDelayedFocusGain(true)
            .setWillPauseWhenDucked(true)
            .setOnAudioFocusChangeListener(focusListener)
            .build()
        val result = manager.requestAudioFocus(audioFocusRequest!!)
        focusPaused = result != AudioManager.AUDIOFOCUS_REQUEST_GRANTED
        applyVoiceEnabled()
    }

    private fun abandonAudioFocus() {
        val manager = audioManager ?: return
        audioFocusRequest?.let { runCatching { manager.abandonAudioFocusRequest(it) } }
        audioFocusRequest = null
        focusPaused = false
    }

    private fun pauseForExternalAudio() {
        if (focusPaused) return
        focusPaused = true
        applyVoiceEnabled()
        sessions.values.forEach { session ->
            runCatching { session.pc.setAudioPlayout(false) }
            runCatching { session.pc.setAudioRecording(false) }
        }
        clearCommunicationRoute()
        audioStatus = "CALL / OTHER AUDIO ACTIVE • RIDEMESH PAUSED"
        listener.onInternetAudioStatus(audioStatus)
    }

    private fun resumeAfterExternalAudio() {
        if (!focusPaused) return
        focusPaused = false
        Thread({
            try {
                Thread.sleep(CALL_RESUME_SETTLE_MS)
            } catch (_: InterruptedException) {
                return@Thread
            }
            if (focusPaused || !running.get()) return@Thread
            selectAudioRoute()
            sessions.values.forEach { session ->
                runCatching { session.pc.setAudioPlayout(true) }
                runCatching { session.pc.setAudioRecording(true) }
            }
            applyVoiceEnabled()
            audioStatus = if (userMuted) {
                "MIC MUTED • LISTENING ONLY"
            } else {
                "WEBRTC OPUS • AUDIO RESUMED"
            }
            listener.onInternetAudioStatus(audioStatus)
        }, "RideMesh-CallResume").apply {
            isDaemon = true
            start()
        }
    }

    private fun applyVoiceEnabled() {
        localAudioTrack?.setEnabled(running.get() && !userMuted && !focusPaused)
    }

    @SuppressLint("MissingPermission")
    private fun clearCommunicationRoute() {
        val manager = audioManager ?: return
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                manager.clearCommunicationDevice()
            } else {
                @Suppress("DEPRECATION")
                runCatching { manager.stopBluetoothSco() }
                @Suppress("DEPRECATION")
                runCatching { manager.isBluetoothScoOn = false }
                @Suppress("DEPRECATION")
                runCatching { manager.isSpeakerphoneOn = false }
            }
            manager.mode = AudioManager.MODE_NORMAL
        } catch (_: Throwable) {
            // Another phone/VoIP call owns the route; RideMesh must not fight it.
        }
    }

    private fun preferOpus(sdp: String): String {
        val separator = if (sdp.contains("\r\n")) "\r\n" else "\n"
        val lines = sdp.split(separator).toMutableList()
        val opusLine = lines.firstOrNull {
            it.startsWith("a=rtpmap:", ignoreCase = true) &&
                it.contains("opus/48000", ignoreCase = true)
        } ?: return sdp

        val opusPt = opusLine.substringAfter("a=rtpmap:").substringBefore(' ').trim()
        val mIndex = lines.indexOfFirst { it.startsWith("m=audio ") }
        if (mIndex >= 0) {
            val parts = lines[mIndex].split(' ').toMutableList()
            if (parts.size > 3) {
                val payloads = parts.drop(3).filter { it != opusPt }
                lines[mIndex] = (parts.take(3) + opusPt + payloads).joinToString(" ")
            }
        }

        val fmtpPrefix = "a=fmtp:$opusPt"
        val fmtpIndex = lines.indexOfFirst { it.startsWith(fmtpPrefix, ignoreCase = true) }
        if (fmtpIndex >= 0) {
            var fmtp = lines[fmtpIndex]
            if (!fmtp.contains("useinbandfec=1", ignoreCase = true)) fmtp += ";useinbandfec=1"
            if (!fmtp.contains("minptime=", ignoreCase = true)) fmtp += ";minptime=10"
            if (!fmtp.contains("stereo=", ignoreCase = true)) fmtp += ";stereo=0"
            lines[fmtpIndex] = fmtp
        } else {
            val rtpIndex = lines.indexOf(opusLine)
            if (rtpIndex >= 0) {
                lines.add(rtpIndex + 1, "$fmtpPrefix minptime=10;useinbandfec=1;stereo=0")
            }
        }
        return lines.joinToString(separator)
    }

    private fun recordError(message: String) {
        lastError = message.take(240)
    }

    // -------------------------------------------------------------------------
    // MQTT 3.1.1 signaling transport
    // -------------------------------------------------------------------------

    private fun sendMqttPublish(topic: String, payload: ByteArray) {
        val topicBytes = topic.toByteArray(Charsets.UTF_8)
        val variable = ByteArrayOutputStream().apply {
            writeUtf8(topicBytes)
            write(payload)
        }.toByteArray()
        sendRaw(fixedPacket(0x30, variable))
    }

    private fun connectPacket(): ByteArray {
        val clientId = "rm4-${nodeId.toString().replace("-", "").take(19)}".toByteArray(Charsets.UTF_8)
        val body = ByteArrayOutputStream().apply {
            writeUtf8("MQTT".toByteArray(Charsets.UTF_8))
            write(0x04)
            write(0x02)
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
            write(0x01)
            writeUtf8(topicBytes)
            write(0x00)
        }.toByteArray()
        return fixedPacket(0x82, body)
    }

    private fun sendRaw(packet: ByteArray) {
        val out = output ?: throw IllegalStateException("Signaling socket not connected")
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

    private fun nextReconnectDelayMs(): Long {
        val exponent = reconnectAttempt.coerceAtMost(3)
        val base = (RECONNECT_BASE_DELAY_MS * (1L shl exponent)).coerceAtMost(RECONNECT_MAX_DELAY_MS)
        reconnectAttempt = (reconnectAttempt + 1).coerceAtMost(8)
        return base + Random.nextLong(0L, RECONNECT_JITTER_MS + 1L)
    }

    private fun closeSocket() {
        signalingConnected.set(false)
        synchronized(outputLock) {
            runCatching { output?.close() }
            output = null
            runCatching { socket?.close() }
            socket = null
        }
    }

    // -------------------------------------------------------------------------
    // Signaling packet encoding
    // -------------------------------------------------------------------------

    private enum class SignalType(val code: Byte) {
        OFFER(1),
        ANSWER(2),
        CANDIDATE(3),
        BYE(4);

        companion object {
            fun from(code: Byte): SignalType? = entries.firstOrNull { it.code == code }
        }
    }

    private data class SignalPacket(
        val from: UUID,
        val to: UUID,
        val type: SignalType,
        val payload: String = "",
        val mid: String = "",
        val line: Int = -1,
    )

    private fun encodeSignal(packet: SignalPacket): ByteArray {
        val payloadBytes = packet.payload.toByteArray(Charsets.UTF_8)
        val midBytes = packet.mid.toByteArray(Charsets.UTF_8)
        val buffer = ByteBuffer.allocate(SIGNAL_FIXED_BYTES + payloadBytes.size + midBytes.size)
            .order(ByteOrder.BIG_ENDIAN)

        buffer.putInt(SIGNAL_MAGIC)
        buffer.put(SIGNAL_VERSION)
        buffer.put(packet.type.code)
        buffer.putLong(packet.from.mostSignificantBits)
        buffer.putLong(packet.from.leastSignificantBits)
        buffer.putLong(packet.to.mostSignificantBits)
        buffer.putLong(packet.to.leastSignificantBits)
        buffer.putInt(packet.line)
        buffer.putInt(payloadBytes.size)
        buffer.putShort(midBytes.size.toShort())
        buffer.put(payloadBytes)
        buffer.put(midBytes)
        return buffer.array()
    }

    private fun decodeSignal(bytes: ByteArray): SignalPacket? {
        if (bytes.size < SIGNAL_FIXED_BYTES) return null
        return try {
            val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
            if (buffer.int != SIGNAL_MAGIC || buffer.get() != SIGNAL_VERSION) return null
            val type = SignalType.from(buffer.get()) ?: return null
            val from = UUID(buffer.long, buffer.long)
            val to = UUID(buffer.long, buffer.long)
            val line = buffer.int
            val payloadLength = buffer.int
            val midLength = buffer.short.toInt() and 0xffff
            if (payloadLength < 0 || payloadLength > MAX_SIGNAL_BYTES) return null
            if (midLength > MAX_MID_BYTES) return null
            if (payloadLength + midLength > buffer.remaining()) return null

            val payloadBytes = ByteArray(payloadLength)
            buffer.get(payloadBytes)
            val midBytes = ByteArray(midLength)
            buffer.get(midBytes)
            SignalPacket(
                from = from,
                to = to,
                type = type,
                payload = payloadBytes.toString(Charsets.UTF_8),
                mid = midBytes.toString(Charsets.UTF_8),
                line = line,
            )
        } catch (_: Throwable) {
            null
        }
    }

    // -------------------------------------------------------------------------
    // Legacy-compatible presence/audio helpers retained for existing unit tests.
    // -------------------------------------------------------------------------

    internal data class PresencePacket(
        val origin: UUID,
        val timestampMs: Long,
        val riderName: String,
        val deviceName: String,
    )

    internal fun encodePresence(packet: PresencePacket): ByteArray {
        val riderBytes = packet.riderName.toByteArray(Charsets.UTF_8).let {
            if (it.size > MAX_RIDER_NAME_BYTES) it.copyOf(MAX_RIDER_NAME_BYTES) else it
        }
        val deviceBytes = packet.deviceName.toByteArray(Charsets.UTF_8).let {
            if (it.size > MAX_DEVICE_NAME_BYTES) it.copyOf(MAX_DEVICE_NAME_BYTES) else it
        }
        return ByteBuffer.allocate(PRESENCE_BASE_BYTES + 1 + riderBytes.size + 1 + deviceBytes.size)
            .order(ByteOrder.BIG_ENDIAN)
            .putLong(packet.origin.mostSignificantBits)
            .putLong(packet.origin.leastSignificantBits)
            .putLong(packet.timestampMs)
            .put(riderBytes.size.toByte())
            .put(riderBytes)
            .put(deviceBytes.size.toByte())
            .put(deviceBytes)
            .array()
    }

    internal fun decodePresence(payload: ByteArray): PresencePacket? {
        if (payload.size < PRESENCE_BASE_BYTES) return null
        return try {
            val buffer = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)
            val origin = UUID(buffer.long, buffer.long)
            val timestamp = buffer.long
            if (!buffer.hasRemaining()) return PresencePacket(origin, timestamp, "", "")

            val riderLength = buffer.get().toInt() and 0xff
            if (riderLength > buffer.remaining()) return PresencePacket(origin, timestamp, "", "")
            val riderBytes = ByteArray(riderLength)
            buffer.get(riderBytes)
            val rider = riderBytes.toString(Charsets.UTF_8).trim()
            if (!buffer.hasRemaining()) return PresencePacket(origin, timestamp, rider, "")

            val deviceLength = buffer.get().toInt() and 0xff
            if (deviceLength > buffer.remaining()) return PresencePacket(origin, timestamp, rider, "")
            val deviceBytes = ByteArray(deviceLength)
            buffer.get(deviceBytes)
            PresencePacket(
                origin,
                timestamp,
                rider,
                deviceBytes.toString(Charsets.UTF_8).trim(),
            )
        } catch (_: Throwable) {
            null
        }
    }

    internal data class InternetPacket(
        val origin: UUID,
        val sequence: Int,
        val timestampMs: Long,
        val audio: ByteArray,
    )

    internal fun encode(packet: InternetPacket): ByteArray {
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

    internal fun decode(bytes: ByteArray): InternetPacket? {
        if (bytes.size < HEADER_BYTES) return null
        return try {
            val buffer = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
            if (buffer.int != MAGIC || buffer.get() != VERSION) return null
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

    private fun sanitizeIdentity(value: String, fallback: String, maxBytes: Int): String {
        val clean = value.trim().replace('|', '/').ifBlank { fallback }
        var result = clean
        while (result.toByteArray(Charsets.UTF_8).size > maxBytes && result.isNotEmpty()) {
            result = result.dropLast(1)
        }
        return result.ifBlank { fallback }
    }

    private open class SimpleSdpObserver : SdpObserver {
        override fun onCreateSuccess(desc: SessionDescription) = Unit
        override fun onSetSuccess() = Unit
        override fun onCreateFailure(error: String) = Unit
        override fun onSetFailure(error: String) = Unit
    }

    companion object {
        private const val PUBLIC_BROKER = "broker.hivemq.com"
        private const val PUBLIC_BROKER_TLS_PORT = 8883
        private const val KEEP_ALIVE_SECONDS = 30
        private const val SOCKET_TIMEOUT_MS = 3_000
        private const val PING_INTERVAL_MS = 12_000L
        private const val PRESENCE_INTERVAL_MS = 2_000L
        private const val PRESENCE_TIMEOUT_MS = 14_000L
        private const val OFFER_RETRY_INTERVAL_MS = 4_000L
        private const val ICE_DISCONNECTED_GRACE_MS = 6_000L
        private const val ICE_FAILED_RETRY_MS = 1_000L
        private const val CALL_RESUME_SETTLE_MS = 650L

        private const val RECONNECT_BASE_DELAY_MS = 1_000L
        private const val RECONNECT_MAX_DELAY_MS = 8_000L
        private const val RECONNECT_JITTER_MS = 500L

        private const val LOCAL_AUDIO_TRACK_ID = "ridemesh-audio"
        private const val MEDIA_STREAM_ID = "ridemesh-stream"
        private const val WEBRTC_NODE_ID_KEY = "beta4_webrtc_node_id"

        private val BROADCAST_ID = UUID(0L, 0L)

        private const val SIGNAL_MAGIC = 0x524D5334 // RMS4
        private const val SIGNAL_VERSION: Byte = 1
        private const val SIGNAL_FIXED_BYTES = 48
        private const val MAX_SIGNAL_BYTES = 128_000
        private const val MAX_MID_BYTES = 512

        private const val PRESENCE_BASE_BYTES = 24
        private const val MAX_RIDER_NAME_BYTES = 48
        private const val MAX_DEVICE_NAME_BYTES = 64

        private const val MAGIC = 0x524D4931 // RMI1 legacy unit-test codec
        private const val VERSION: Byte = 1
        private const val HEADER_BYTES = 33
    }
}
