package com.bikemesh.ridemesh

import android.Manifest
import android.app.AlertDialog
import android.bluetooth.BluetoothManager
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.res.ColorStateList
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.bikemesh.ridemesh.audio.AudioEngine
import com.bikemesh.ridemesh.beta.BetaWindow
import com.bikemesh.ridemesh.audio.AudioRoute
import com.bikemesh.ridemesh.databinding.ActivityMainBinding
import com.bikemesh.ridemesh.mesh.LobbyNode
import com.bikemesh.ridemesh.mesh.MeshNode
import com.bikemesh.ridemesh.service.RideService
import com.bikemesh.ridemesh.transport.InternetNode
import com.google.android.gms.mlkit.barcode.GmsBarcodeScannerOptions
import com.google.android.gms.mlkit.barcode.GmsBarcodeScanning
import com.google.android.material.button.MaterialButton
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import kotlin.random.Random

class MainActivity : AppCompatActivity(), MeshNode.Listener, LobbyNode.Listener, InternetNode.Listener {
    private lateinit var binding: ActivityMainBinding
    private lateinit var meshNode: MeshNode
    private lateinit var lobbyNode: LobbyNode
    private lateinit var internetNode: InternetNode
    private lateinit var audioEngine: AudioEngine

    private val prefs by lazy { getSharedPreferences("ridemesh", MODE_PRIVATE) }
    private val nearbyButtons = linkedMapOf<String, MaterialButton>()
    private val mainHandler = Handler(Looper.getMainLooper())
    private val speakingUntilMs = ConcurrentHashMap<String, Long>()

    private var rideStarted = false
    private var pendingAction = PendingAction.NONE
    private var directPeerCount = 0
    private var internetPeerCount = 0
    private var meshRunning = false
    private var internetConnectedSinceMs = 0L
    private var lastMeshRefreshMs = 0L
    private var micMuted = false
    private var betaExpiredDialogShown = false
    private var transportMode = TransportMode.AUTO
    private var meshLabRole = MeshNode.LabRole.NORMAL

    private enum class TransportMode { AUTO, LOCAL_ONLY, INTERNET_ONLY }
    private enum class PendingAction { NONE, START_RIDE, FIND_RIDERS }
    private enum class Screen { HOME, SETUP, ACTIVE }

    private data class RiderTile(
        val key: String,
        val name: String,
        val device: String,
        val qualityBars: Int,
        val path: String,
        val self: Boolean = false,
    )

    private val stopLobbyScan = Runnable {
        lobbyNode.stop()
        binding.findNearby.text = "FIND NEARBY RIDERS"
        if (rideStarted) {
            log("Nearby invite scan finished")
            if (!internetNode.isConnected() || !binding.batterySaver.isChecked) {
                ensureLocalMeshRunning("invite scan finished")
            }
        } else {
            log("Nearby scan paused to save battery. Tap FIND to scan again.")
        }
    }

    /**
     * Keeps the ride recoverable after a complete outage.
     * InternetNode independently retries the Internet relay. When Internet is
     * absent, local mesh stays awake and periodically refreshes discovery.
     */
    private val rideWatchdog = object : Runnable {
        override fun run() {
            if (!rideStarted) return
            if (isBetaExpired()) {
                expireActiveRide()
                return
            }

            val now = System.currentTimeMillis()
            when (transportMode) {
                TransportMode.LOCAL_ONLY -> {
                    ensureLocalMeshRunning("LOCAL MESH ONLY")
                    if (meshRunning && directPeerCount == 0 && now - lastMeshRefreshMs >= LOCAL_MESH_REFRESH_MS) {
                        restartLocalMesh()
                    }
                }

                TransportMode.INTERNET_ONLY -> {
                    if (meshRunning) sleepLocalMesh("INTERNET ONLY")
                }

                TransportMode.AUTO -> {
                    if (internetNode.isConnected()) {
                        val stableFor = now - internetConnectedSinceMs
                        if (binding.batterySaver.isChecked && stableFor >= INTERNET_STABLE_BEFORE_MESH_SLEEP_MS) {
                            sleepLocalMesh("Internet stable")
                        } else {
                            ensureLocalMeshRunning("warm handover fallback")
                        }
                    } else {
                        ensureLocalMeshRunning("Internet unavailable")
                        if (meshRunning && directPeerCount == 0 && now - lastMeshRefreshMs >= LOCAL_MESH_REFRESH_MS) {
                            restartLocalMesh()
                        }
                    }
                }
            }

            updateTransportStatus()
            updateCapturePolicy()
            mainHandler.postDelayed(this, WATCHDOG_INTERVAL_MS)
        }
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        if (!hasRequiredPermissions()) {
            log("Required microphone / nearby permission was denied")
            pendingAction = PendingAction.NONE
            return@registerForActivityResult
        }

        val action = pendingAction
        pendingAction = PendingAction.NONE
        when (action) {
            PendingAction.START_RIDE -> startRideNow()
            PendingAction.FIND_RIDERS -> startNearbyLobby()
            PendingAction.NONE -> Unit
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        restoreSettings()
        ensureBetaFirstLaunch()

        meshNode = MeshNode(applicationContext, this)
        lobbyNode = LobbyNode(applicationContext, this)
        internetNode = InternetNode(this, applicationContext)
        audioEngine = AudioEngine(
            context = applicationContext,
            onCapturedFrame = ::sendHybridAudio,
            onStatus = { text -> runOnUiThread { updateAudioUi(text) } },
        )

        applySelectedAudioRoute()
        showScreen(Screen.HOME)
        clearNearbyRiders("Tap FIND to discover RideMesh riders nearby.")
        applyPowerUi()

        binding.createRide.setOnClickListener {
            if (!ensureBetaUsable()) return@setOnClickListener
            binding.setupTitle.text = "CREATE RIDE"
            binding.rideCode.setText(generateRideCode())
            showScreen(Screen.SETUP)
        }

        binding.joinRide.setOnClickListener {
            if (!ensureBetaUsable()) return@setOnClickListener
            binding.setupTitle.text = "JOIN RIDE"
            showScreen(Screen.SETUP)
            binding.rideCode.requestFocus()
        }

        binding.backHome.setOnClickListener {
            stopLobbyDiscovery()
            showScreen(Screen.HOME)
        }

        binding.openSettings.setOnClickListener { showSettingsAndHelpDialog() }
        binding.activeStop.setOnClickListener { confirmStopRide() }
        binding.activeMute.setOnClickListener { setMicMuted(!micMuted) }
        binding.activeRiders.setOnClickListener { showRidersDialog() }
        binding.activeInvite.setOnClickListener { showLiveInviteOptions() }
        binding.activeAudio.setOnClickListener { showAudioRouteDialog() }
        binding.activeStatus.setOnClickListener { showRideStatusDialog() }

        binding.audioRoute.setOnCheckedChangeListener { _, _ ->
            applySelectedAudioRoute()
            saveSettings()
        }

        binding.batterySaver.setOnCheckedChangeListener { _, _ ->
            saveSettings()
            applyBatteryPolicy()
        }

        binding.startRide.setOnClickListener {
            if (rideStarted) stopRide() else ensurePermissionsAndRun(PendingAction.START_RIDE)
        }

        binding.findNearby.visibility = View.GONE
        binding.nearbyUsers.visibility = View.GONE

        binding.showQr.setOnClickListener { showRideQr() }
        binding.scanQr.setOnClickListener { scanRideQr() }

        refreshBetaAccessUi(showWarning = true)
        updateMuteUi()
    }

    private fun showScreen(screen: Screen) {
        binding.screenHome.visibility = if (screen == Screen.HOME) View.VISIBLE else View.GONE
        binding.screenSetup.visibility = if (screen == Screen.SETUP) View.VISIBLE else View.GONE
        binding.screenActive.visibility = if (screen == Screen.ACTIVE) View.VISIBLE else View.GONE
    }

    private fun ensurePermissionsAndRun(action: PendingAction) {
        if (action == PendingAction.START_RIDE && !ensureBetaUsable()) return
        val missing = requiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) {
            when (action) {
                PendingAction.START_RIDE -> startRideNow()
                PendingAction.FIND_RIDERS -> startNearbyLobby()
                PendingAction.NONE -> Unit
            }
        } else {
            pendingAction = action
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    /**
     * Starts a short lobby scan. During an active ride we only do this while the
     * Internet voice path is healthy, so adding riders cannot interrupt a local-only call.
     */
    private fun startNearbyLobby() {
        if (!radiosReady()) {
            log("Nearby riders unavailable: turn ON Bluetooth and Wi-Fi, then try again")
            return
        }

        if (rideStarted && !internetNode.isConnected()) {
            AlertDialog.Builder(this)
                .setTitle("Keep local voice uninterrupted")
                .setMessage("Nearby rider scanning during a local-only mesh call can compete with the same radio. Share the QR now, or use FIND NEARBY when Internet voice is available.")
                .setPositiveButton("SHARE QR") { _, _ -> shareRideQr() }
                .setNegativeButton("CLOSE", null)
                .show()
            return
        }

        stopLobbyDiscovery()
        clearNearbyRiders("Scanning nearby…")

        if (rideStarted && meshRunning) {
            // Voice stays on Internet while the short invite scan uses Nearby.
            sleepLocalMesh("live nearby invite scan")
        }

        lobbyNode.start(
            binding.riderName.text?.toString().orEmpty(),
            normalizedRideCode(),
        )
        binding.findNearby.text = "SCANNING…"
        mainHandler.postDelayed(stopLobbyScan, LOBBY_SCAN_WINDOW_MS)
        log(if (rideStarted) "Live nearby rider scan started • Internet voice continues" else "Short nearby scan started")
    }

    private fun stopLobbyDiscovery() {
        mainHandler.removeCallbacks(stopLobbyScan)
        if (::lobbyNode.isInitialized) lobbyNode.stop()
        if (::binding.isInitialized) binding.findNearby.text = "FIND NEARBY RIDERS"
    }

    private fun showLiveInviteOptions() {
        val options = arrayOf(
            "Show QR code",
            "Share QR code",
        )
        AlertDialog.Builder(this)
            .setTitle("Invite riders")
            .setItems(options) { _, which ->
                when (which) {
                    0 -> showRideQr()
                    1 -> shareRideQr()
                }
            }
            .setNegativeButton("CLOSE", null)
            .show()
    }

    private fun buildRideQrBitmap(code: String): Bitmap {
        val payload = "ridemesh://join?ride=${Uri.encode(code)}"
        val size = 720
        val matrix = QRCodeWriter().encode(payload, BarcodeFormat.QR_CODE, size, size)
        return Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888).apply {
            for (y in 0 until size) {
                for (x in 0 until size) {
                    setPixel(x, y, if (matrix[x, y]) Color.BLACK else Color.WHITE)
                }
            }
        }
    }

    private fun showRideQr() {
        val code = normalizedRideCode()
        binding.rideCode.setText(code)
        saveSettings()

        try {
            val bitmap = buildRideQrBitmap(code)
            val image = ImageView(this).apply {
                setImageBitmap(bitmap)
                adjustViewBounds = true
                setPadding(24, 24, 24, 24)
            }

            AlertDialog.Builder(this)
                .setTitle("Invite to $code")
                .setMessage("Scan this QR to join. Your current conversation stays active.")
                .setView(image)
                .setPositiveButton("SHARE") { _, _ -> shareRideQr() }
                .setNegativeButton("CLOSE", null)
                .show()
            log("Showing QR invite for $code")
        } catch (t: Throwable) {
            log("Could not create QR: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    private fun shareRideQr() {
        val code = normalizedRideCode()
        try {
            val bitmap = buildRideQrBitmap(code)
            val shareDir = File(cacheDir, "shared").apply { mkdirs() }
            val file = File(shareDir, "RideMesh-$code.png")
            FileOutputStream(file).use { out ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)
            }
            val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "image/png"
                putExtra(Intent.EXTRA_STREAM, uri)
                putExtra(Intent.EXTRA_TEXT, "Join my RideMesh ride: $code\nOpen RideMesh → Join a Ride → Scan QR")
                clipData = ClipData.newUri(contentResolver, "RideMesh invite QR", uri)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            startActivity(Intent.createChooser(intent, "Share RideMesh QR"))
        } catch (t: Throwable) {
            log("Could not share QR: ${t.message ?: t.javaClass.simpleName}")
            AlertDialog.Builder(this)
                .setTitle("Could not share QR")
                .setMessage("Ride code: $code")
                .setPositiveButton("OK", null)
                .show()
        }
    }

    private fun scanRideQr() {
        val options = GmsBarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
            .enableAutoZoom()
            .build()

        GmsBarcodeScanning.getClient(this, options).startScan()
            .addOnSuccessListener { barcode ->
                val code = parseRideQr(barcode.rawValue.orEmpty())
                if (code == null) {
                    log("That QR is not a RideMesh invite")
                    return@addOnSuccessListener
                }

                binding.rideCode.setText(code)
                saveSettings()
                AlertDialog.Builder(this)
                    .setTitle("Join $code?")
                    .setMessage("Ride code loaded successfully.")
                    .setNegativeButton("LATER", null)
                    .setPositiveButton("JOIN") { _, _ ->
                        ensurePermissionsAndRun(PendingAction.START_RIDE)
                    }
                    .show()
            }
            .addOnCanceledListener { log("QR scan cancelled") }
            .addOnFailureListener { log("QR scanner error: ${it.message ?: "unknown"}") }
    }

    private fun parseRideQr(raw: String): String? = runCatching {
        val uri = Uri.parse(raw)
        if (!uri.scheme.equals("ridemesh", true) || !uri.host.equals("join", true)) {
            return@runCatching null
        }
        uri.getQueryParameter("ride")
            ?.trim()
            ?.uppercase()
            ?.takeIf { it.isNotBlank() }
            ?.take(12)
    }.getOrNull()

    private fun startRideNow() {
        if (rideStarted || !ensureBetaUsable()) return

        setMicMuted(false)
        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val code = normalizedRideCode()
        binding.riderName.setText(rider)
        binding.rideCode.setText(code)
        transportMode = TransportMode.INTERNET_ONLY
        meshLabRole = MeshNode.LabRole.NORMAL
        saveSettings()

        try {
            stopLobbyDiscovery()
            startRideServiceSafely()

            rideStarted = true
            directPeerCount = 0
            internetPeerCount = 0
            meshRunning = false
            internetConnectedSinceMs = 0L
            lastMeshRefreshMs = 0L

            // Beta4 voice is captured and rendered directly by WebRTC. The old PCM
            // AudioEngine stays idle so it cannot create a second microphone/audio path.
            internetNode.start(code, rider, deviceLabel())
            internetNode.setMuted(micMuted)
            applySelectedAudioRoute()

            binding.activeRideCode.text = code
            showScreen(Screen.ACTIVE)
            updateTransportStatus()
            updateCapturePolicy()

            mainHandler.removeCallbacks(rideWatchdog)
            mainHandler.postDelayed(rideWatchdog, WATCHDOG_INTERVAL_MS)
            log("Ride started • INTERNET WEBRTC + OPUS • call-safe audio focus enabled")
        } catch (t: Throwable) {
            recoverFromStartFailure(t)
        }
    }

    private fun sendHybridAudio(audio: ByteArray) {
        // Beta4 does not send PCM frames from this legacy engine. WebRTC owns voice capture.
    }

    private fun ensureLocalMeshRunning(reason: String) {
        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || meshRunning) return
        if (!radiosReady()) {
            log("LOCAL MESH BLOCKED • ${localRadioSummary()}")
            return
        }
        meshNode.start(
            binding.riderName.text?.toString().orEmpty(),
            normalizedRideCode(),
            meshLabRole,
            deviceLabel(),
            preferOffline = transportMode == TransportMode.LOCAL_ONLY,
        )
        meshRunning = true
        lastMeshRefreshMs = System.currentTimeMillis()
        log("Local mesh awake • $reason • role ${meshLabRole.name}")
    }

    private fun sleepLocalMesh(reason: String) {
        if (!meshRunning) return
        meshRunning = false
        meshNode.stop()
        directPeerCount = 0
        log("Local mesh sleeping • $reason")
    }

    private fun restartLocalMesh() {
        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY || !radiosReady()) return
        if (transportMode == TransportMode.AUTO && internetNode.isConnected()) return
        if (meshRunning) {
            meshNode.refreshDiscovery("automatic reconnect")
            lastMeshRefreshMs = System.currentTimeMillis()
            log("Refreshing local advertising/discovery without dropping endpoints")
        } else {
            ensureLocalMeshRunning("automatic reconnect")
        }
    }

    private fun restartLocalMeshForRoleOrMode(reason: String) {
        if (!rideStarted || transportMode == TransportMode.INTERNET_ONLY) return
        if (meshRunning) {
            meshRunning = false
            meshNode.stop()
            directPeerCount = 0
            mainHandler.postDelayed({
                if (rideStarted && transportMode != TransportMode.INTERNET_ONLY) {
                    ensureLocalMeshRunning(reason)
                    updateTransportStatus()
                    updateCapturePolicy()
                }
            }, LOCAL_MESH_RESTART_SETTLE_MS)
        } else {
            ensureLocalMeshRunning(reason)
        }
    }

    private fun applyBatteryPolicy() {
        applyPowerUi()
        if (!rideStarted) return

        when (transportMode) {
            TransportMode.LOCAL_ONLY -> ensureLocalMeshRunning("LOCAL ONLY ignores mesh sleep")
            TransportMode.INTERNET_ONLY -> if (meshRunning) sleepLocalMesh("INTERNET ONLY")
            TransportMode.AUTO -> {
                if (!binding.batterySaver.isChecked) {
                    ensureLocalMeshRunning("Max Link selected")
                } else if (!internetNode.isConnected()) {
                    ensureLocalMeshRunning("Internet unavailable")
                }
            }
        }

        updateTransportStatus()
        updateCapturePolicy()
    }

    private fun updateCapturePolicy() {
        if (!rideStarted) return
        val status = when {
            micMuted -> "MIC MUTED • LISTENING ONLY"
            internetNode.voicePeerCount() > 0 -> internetNode.currentAudioStatus()
            internetNode.isConnected() -> "WEBRTC SIGNALING READY • WAITING FOR RIDERS"
            else -> "WEBRTC CONNECTING • MIC READY"
        }
        updateAudioUi(status)
    }

    private fun startRideServiceSafely() {
        try {
            ContextCompat.startForegroundService(this, Intent(this, RideService::class.java))
        } catch (t: Throwable) {
            log("Background ride service unavailable: ${t.javaClass.simpleName}. App must remain open.")
        }
    }

    private fun recoverFromStartFailure(t: Throwable) {
        mainHandler.removeCallbacks(rideWatchdog)
        runCatching { audioEngine.stopTransmit() }
        runCatching { internetNode.stop() }
        runCatching { meshNode.stop() }
        runCatching { stopService(Intent(this, RideService::class.java)) }

        rideStarted = false
        meshRunning = false
        directPeerCount = 0
        internetPeerCount = 0
        internetConnectedSinceMs = 0L
        log("START ERROR — ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")
        showScreen(Screen.SETUP)

        AlertDialog.Builder(this)
            .setTitle("Could not start ride")
            .setMessage("RideMesh stayed open. Check Internet access and microphone permission, then try again.")
            .setPositiveButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }
            .setNegativeButton("CLOSE", null)
            .show()
    }

    private fun bluetoothReady(): Boolean = try {
        getSystemService(BluetoothManager::class.java).adapter?.isEnabled == true
    } catch (_: Throwable) {
        false
    }

    private fun wifiReady(): Boolean = try {
        applicationContext.getSystemService(WifiManager::class.java).isWifiEnabled
    } catch (_: Throwable) {
        false
    }

    private fun radiosReady(): Boolean = bluetoothReady() && wifiReady()

    private fun localRadioSummary(): String {
        val missing = requiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }.map { it.substringAfterLast('.') }
        return "Wi-Fi ${if (wifiReady()) "ON" else "OFF"} • Bluetooth ${if (bluetoothReady()) "ON" else "OFF"} • Permissions ${if (missing.isEmpty()) "OK" else "MISSING ${missing.joinToString()}"}"
    }

    private fun confirmStopRide() {
        AlertDialog.Builder(this)
            .setTitle("End ride?")
            .setMessage("This disconnects your RideMesh voice session.")
            .setNegativeButton("CANCEL", null)
            .setPositiveButton("END RIDE") { _, _ -> stopRide() }
            .show()
    }

    private fun stopRide() {
        mainHandler.removeCallbacks(rideWatchdog)
        stopLobbyDiscovery()
        audioEngine.stopTransmit()
        internetNode.stop()
        meshRunning = false
        meshNode.stop()
        stopService(Intent(this, RideService::class.java))

        rideStarted = false
        directPeerCount = 0
        internetPeerCount = 0
        internetConnectedSinceMs = 0L
        binding.riderCount.text = "RIDE ACTIVE"
        binding.meshStatus.text = "CONNECTING…"
        binding.networkTile.text = "CONNECTING"
        binding.homeNetworkStatus.text = "WebRTC Voice\nReady"
        binding.activeRiders.text = "RIDERS"
        binding.riderGrid.removeAllViews()
        speakingUntilMs.clear()
        setMicMuted(false)
        log("Ride stopped")
        showScreen(Screen.HOME)
        refreshBetaAccessUi(showWarning = false)
    }

    private fun applySelectedAudioRoute() {
        if (!::internetNode.isInitialized) return
        val route = when (binding.audioRoute.checkedRadioButtonId) {
            R.id.routePhone -> "PHONE"
            R.id.routeHelmet -> "HELMET"
            else -> "AUTO"
        }
        if (rideStarted) updateAudioUi(internetNode.setAudioRoute(route))
        else internetNode.setAudioRoute(route)
    }

    private fun updateAudioUi(text: String) {
        binding.audioStatus.text = if (micMuted) "MIC MUTED • LISTENING ONLY" else text
        binding.homeAudioStatus.text = when {
            micMuted -> "Listening Only\nMic Muted"
            text.contains("Bluetooth", true) || text.contains("headset", true) -> "Connected\nHelmet Audio"
            text.contains("sleep", true) || text.contains("Reconnect", true) || text.contains("Waiting", true) -> "Audio Link\nWaiting"
            else -> "Phone Audio\nReady"
        }

        binding.audioTile.text = when {
            micMuted -> "MIC MUTED"
            text.contains("Bluetooth", true) || text.contains("headset", true) -> "HELMET AUDIO"
            text.contains("sleep", true) || text.contains("Reconnect", true) || text.contains("Waiting", true) -> "MIC STANDBY"
            else -> "VOICE CLEAN"
        }
    }

    private fun setMicMuted(muted: Boolean) {
        micMuted = muted
        if (::internetNode.isInitialized) internetNode.setMuted(muted)
        if (::binding.isInitialized) updateMuteUi()
    }

    private fun updateMuteUi() {
        val color = ContextCompat.getColor(this, if (micMuted) R.color.danger else R.color.panel2)
        val stroke = ContextCompat.getColor(this, if (micMuted) R.color.danger else R.color.accent)
        binding.activeMute.text = if (micMuted) "MIC MUTED" else "MUTE MIC"
        binding.activeMute.backgroundTintList = ColorStateList.valueOf(color)
        binding.activeMute.strokeColor = ColorStateList.valueOf(stroke)
        binding.activeMute.setTextColor(ContextCompat.getColor(this, R.color.white))
    }

    private fun restoreSettings() {
        val savedRider = prefs.getString("rider", "").orEmpty()
        binding.riderName.setText(
            savedRider.takeIf { it.isNotBlank() && !it.equals(Build.MODEL, ignoreCase = true) } ?: "Rider"
        )
        binding.rideCode.setText(prefs.getString("code", "RIDE01"))
        binding.batterySaver.isChecked = prefs.getBoolean("battery_smart", true)
        transportMode = TransportMode.INTERNET_ONLY
        meshLabRole = MeshNode.LabRole.NORMAL

        when (prefs.getString("audio_route", "AUTO")) {
            "PHONE" -> binding.routePhone.isChecked = true
            "HELMET" -> binding.routeHelmet.isChecked = true
            else -> binding.routeAuto.isChecked = true
        }
    }

    private fun saveSettings() {
        val audioRoute = when (binding.audioRoute.checkedRadioButtonId) {
            R.id.routePhone -> "PHONE"
            R.id.routeHelmet -> "HELMET"
            else -> "AUTO"
        }

        prefs.edit()
            .putString("rider", binding.riderName.text?.toString().orEmpty())
            .putString("code", normalizedRideCode())
            .putString("audio_route", audioRoute)
            .putBoolean("battery_smart", binding.batterySaver.isChecked)
            .putString("transport_mode", transportMode.name)
            .putString("mesh_lab_role", meshLabRole.name)
            .apply()
    }

    private fun normalizedRideCode(): String = binding.rideCode.text
        ?.toString()
        .orEmpty()
        .trim()
        .uppercase()
        .ifBlank { "RIDE01" }
        .take(12)

    private fun generateRideCode(): String = "RM" + Random.nextInt(1000, 9999)

    private fun deviceLabel(): String {
        val manufacturer = Build.MANUFACTURER.trim()
            .replaceFirstChar { if (it.isLowerCase()) it.titlecase(Locale.ROOT) else it.toString() }
        val model = Build.MODEL.trim()
        return when {
            model.isBlank() -> manufacturer.ifBlank { "Android device" }
            manufacturer.isBlank() -> model
            model.startsWith(manufacturer, ignoreCase = true) -> model
            else -> "$manufacturer $model"
        }.take(48)
    }

    private fun hasRequiredPermissions(): Boolean = requiredPermissions().all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun requiredPermissions(): List<String> = buildList {
        add(Manifest.permission.RECORD_AUDIO)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            add(Manifest.permission.BLUETOOTH_CONNECT)
        }
    }

    override fun onLog(message: String) {
        runOnUiThread { log(message) }
    }

    override fun onDirectPeerCount(count: Int) {
        directPeerCount = count
        if (count > 0) lastMeshRefreshMs = System.currentTimeMillis()
        runOnUiThread {
            updateTransportStatus()
            updateCapturePolicy()
        }
    }

    override fun onAudioPacket(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {
        if (!rideStarted) return
        val tileKey = meshNode.endpointIdForSource(sourceId) ?: sourceId
        markRiderSpeaking(tileKey)
        audioEngine.playIncoming(sourceId, sequence, timestampMs, audio)
    }

    override fun onInternetState(connected: Boolean, message: String) {
        runOnUiThread {
            log(message)
            internetConnectedSinceMs = if (connected) System.currentTimeMillis() else 0L
            updateTransportStatus()
            updateCapturePolicy()
        }
    }

    override fun onInternetPeerCount(count: Int) {
        internetPeerCount = count
        runOnUiThread { updateTransportStatus() }
    }

    override fun onInternetAudio(sourceId: String, sequence: Int, timestampMs: Long, audio: ByteArray) {
        // Beta4 WebRTC renders remote audio internally. Legacy PCM callback is intentionally unused.
    }

    override fun onInternetAudioStatus(message: String) {
        runOnUiThread {
            if (rideStarted) updateAudioUi(message)
        }
    }

    private fun updateTransportStatus() {
        if (!rideStarted) return
        val diag = internetNode.diagnostics()

        binding.networkTile.text = when {
            diag.voicePeersConnected > 0 -> "WEBRTC"
            diag.signalingConnected -> "INTERNET"
            else -> "NET SEARCH"
        }
        binding.riderCount.text = "RIDE ACTIVE"
        binding.meshStatus.text = when {
            diag.voicePeersConnected > 0 ->
                "OPUS VOICE • ${diag.voicePeersConnected} DIRECT PEER${if (diag.voicePeersConnected == 1) "" else "S"}"
            diag.signalingConnected -> "SIGNALING READY • WAITING FOR RIDERS"
            else -> "INTERNET RECONNECTING • WEBRTC AUTO RETRY"
        }
        binding.homeNetworkStatus.text = if (internetNode.isConnected()) {
            "WebRTC Voice\nActive"
        } else {
            "WebRTC Voice\nReady"
        }

        val visibleRiderTotal = if (internetNode.isConnected()) internetPeerCount + 1 else 1
        binding.activeRiders.text = "RIDERS $visibleRiderTotal"
        renderRiderGrid()
        applyPowerUi()
    }

    private fun markRiderSpeaking(key: String) {
        val expires = System.currentTimeMillis() + SPEAKING_HOLD_MS
        speakingUntilMs[key] = expires
        runOnUiThread {
            renderRiderGrid()
            mainHandler.postDelayed({
                val current = speakingUntilMs[key] ?: return@postDelayed
                if (System.currentTimeMillis() >= current) {
                    speakingUntilMs.remove(key, current)
                    renderRiderGrid()
                }
            }, SPEAKING_HOLD_MS + 40L)
        }
    }

    private fun renderRiderGrid() {
        if (!rideStarted || !::binding.isInitialized) return

        val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val meDevice = deviceLabel()
        val riders = mutableListOf(
            RiderTile(
                key = SELF_TILE_KEY,
                name = me,
                device = meDevice,
                qualityBars = if (internetNode.isConnected() || directPeerCount > 0) 4 else 1,
                path = if (internetNode.isConnected()) "Internet" else if (directPeerCount > 0) "Local" else "Searching",
                self = true,
            )
        )

        if (internetNode.isConnected()) {
            internetNode.remotePeers().forEach { peer ->
                riders += RiderTile(
                    key = peer.id.toString(),
                    name = peer.displayName,
                    device = peer.deviceName,
                    qualityBars = peer.qualityBars,
                    path = "Internet",
                )
            }
        } else if (meshRunning) {
            meshNode.directPeers().forEach { peer ->
                riders += RiderTile(
                    key = peer.endpointId,
                    name = peer.displayName,
                    device = peer.deviceName,
                    qualityBars = peer.qualityBars,
                    path = "Local",
                )
            }
        }

        val visible = riders.take(MAX_VISIBLE_RIDER_TILES)
        val grid = binding.riderGrid
        grid.removeAllViews()
        grid.columnCount = 3
        grid.rowCount = if (visible.size <= 3) 1 else 2

        val positions = riderPositions(visible.size)
        visible.forEachIndexed { index, rider ->
            val (row, col) = positions[index]
            grid.addView(buildRiderTile(rider), GridLayout.LayoutParams().apply {
                rowSpec = GridLayout.spec(row)
                columnSpec = GridLayout.spec(col, 1f)
                width = 0
                height = dp(136)
                setMargins(dp(3), dp(3), dp(3), dp(3))
            })
        }
    }

    private fun buildRiderTile(rider: RiderTile): View {
        val speaking = (speakingUntilMs[rider.key] ?: 0L) > System.currentTimeMillis()
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(dp(3), dp(3), dp(3), dp(2))
        }

        val avatar = TextView(this).apply {
            text = rider.name.trim().firstOrNull()?.uppercaseChar()?.toString() ?: "R"
            gravity = Gravity.CENTER
            textSize = 30f
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#101918"))
                setStroke(
                    dp(if (speaking) 3 else 1),
                    if (speaking) ContextCompat.getColor(this@MainActivity, R.color.accent)
                    else ContextCompat.getColor(this@MainActivity, R.color.border)
                )
            }
        }
        card.addView(avatar, LinearLayout.LayoutParams(dp(72), dp(72)))

        val name = TextView(this).apply {
            text = rider.name.ifBlank { "Rider" }
            gravity = Gravity.CENTER
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            textSize = 14.5f
            setTextColor(
                ContextCompat.getColor(
                    this@MainActivity,
                    if (speaking) R.color.accent else R.color.white
                )
            )
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        }
        card.addView(name, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(26)).apply {
            topMargin = dp(5)
        })

        val quality = TextView(this).apply {
            text = if (rider.self) "YOU  ${qualityGlyphs(rider.qualityBars)}" else qualityGlyphs(rider.qualityBars)
            gravity = Gravity.CENTER
            textSize = 11.5f
            setTextColor(qualityColor(rider.qualityBars))
        }
        card.addView(quality, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(20)))
        return card
    }

    private fun riderPositions(count: Int): List<Pair<Int, Int>> = when (count.coerceIn(1, 6)) {
        1 -> listOf(0 to 1)
        2 -> listOf(0 to 0, 0 to 2)
        3 -> listOf(0 to 0, 0 to 1, 0 to 2)
        4 -> listOf(0 to 0, 0 to 2, 1 to 0, 1 to 2)
        5 -> listOf(0 to 0, 0 to 1, 0 to 2, 1 to 0, 1 to 2)
        else -> listOf(0 to 0, 0 to 1, 0 to 2, 1 to 0, 1 to 1, 1 to 2)
    }

    private fun qualityGlyphs(bars: Int): String {
        val clamped = bars.coerceIn(1, 4)
        val levels = arrayOf("▂", "▄", "▆", "█")
        return levels.mapIndexed { index, glyph -> if (index < clamped) glyph else "·" }.joinToString("")
    }

    private fun qualityColor(bars: Int): Int = when (bars.coerceIn(1, 4)) {
        1 -> Color.parseColor("#FF6B6B")
        2 -> ContextCompat.getColor(this, R.color.amber)
        else -> ContextCompat.getColor(this, R.color.accent)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun applyPowerUi() {
        binding.powerTile.text = if (binding.batterySaver.isChecked) "SMART POWER" else "MAX LINK"
        binding.powerTile.setTextColor(
            ContextCompat.getColor(this, if (binding.batterySaver.isChecked) R.color.green else R.color.amber)
        )
    }

    override fun onLobbyLog(message: String) {
        runOnUiThread { log(message) }
    }

    override fun onNearbyRiderFound(endpointId: String, riderName: String, rideCode: String) {
        runOnUiThread {
            if (nearbyButtons.containsKey(endpointId)) return@runOnUiThread

            val marker = MaterialButton(this).apply {
                isAllCaps = false
                text = "$riderName   •   $rideCode     INVITE"
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
                strokeColor = ContextCompat.getColorStateList(this@MainActivity, R.color.border)
                setOnClickListener {
                    lobbyNode.invite(endpointId, normalizedRideCode(), binding.riderName.text?.toString().orEmpty())
                }
            }
            nearbyButtons[endpointId] = marker

            if (rideStarted) {
                AlertDialog.Builder(this)
                    .setTitle("Nearby RideMesh rider found")
                    .setMessage("$riderName is nearby${if (rideCode.isNotBlank()) " • currently showing $rideCode" else ""}. Invite them to ${normalizedRideCode()}?\n\nYour current Internet conversation continues while you invite.")
                    .setPositiveButton("INVITE") { _, _ ->
                        lobbyNode.invite(endpointId, normalizedRideCode(), binding.riderName.text?.toString().orEmpty())
                    }
                    .setNegativeButton("LATER", null)
                    .show()
            } else {
                if (nearbyButtons.size == 1) binding.nearbyUsers.removeAllViews()
                binding.nearbyUsers.addView(marker)
            }
        }
    }

    override fun onNearbyRiderLost(endpointId: String) {
        runOnUiThread {
            val button = nearbyButtons.remove(endpointId) ?: return@runOnUiThread
            binding.nearbyUsers.removeView(button)
            if (!rideStarted && nearbyButtons.isEmpty()) {
                clearNearbyRiders("No riders visible. Tap FIND to scan again.")
            }
        }
    }

    override fun onRideInviteReceived(inviterName: String, rideCode: String) {
        runOnUiThread {
            if (rideStarted) {
                val sameRide = normalizedRideCode().equals(rideCode, true)
                AlertDialog.Builder(this)
                    .setTitle(if (sameRide) "Already in this ride" else "Ride invitation received")
                    .setMessage(if (sameRide) "$inviterName invited you to the ride you are already using." else "$inviterName invited you to $rideCode. End your current ride before switching groups.")
                    .setPositiveButton("OK", null)
                    .show()
                return@runOnUiThread
            }

            AlertDialog.Builder(this)
                .setTitle("Ride invitation")
                .setMessage("$inviterName invited you to $rideCode")
                .setNegativeButton("DECLINE", null)
                .setPositiveButton("JOIN") { _, _ ->
                    binding.rideCode.setText(rideCode)
                    saveSettings()
                    stopLobbyDiscovery()
                    ensurePermissionsAndRun(PendingAction.START_RIDE)
                }
                .show()
        }
    }

    private fun showRidersDialog() {
        val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val meDevice = deviceLabel()
        val internetPeers = if (internetNode.isConnected()) internetNode.remotePeers() else emptyList()
        val localPeers = if (meshRunning) meshNode.directPeers() else emptyList()
        val riderLines = linkedMapOf<String, String>()

        internetPeers.forEach { peer ->
            val device = peer.deviceName.ifBlank { "Android device" }
            val key = "${peer.displayName}|$device".lowercase(Locale.ROOT)
            riderLines[key] = "• ${peer.displayName}\n  $device • Internet"
        }

        localPeers.forEach { peer ->
            val device = peer.deviceName.ifBlank { "Android device" }
            val key = "${peer.displayName}|$device".lowercase(Locale.ROOT)
            if (!riderLines.containsKey(key)) {
                riderLines[key] = "• ${peer.displayName}\n  $device • Local mesh"
            }
        }

        val message = buildString {
            append("YOU\n")
            append("• $me\n")
            append("  $meDevice\n\n")

            append("CONNECTED RIDERS")
            if (riderLines.isEmpty()) {
                append("\nWaiting for another rider…")
            } else {
                append(" (${riderLines.size})\n")
                append(riderLines.values.joinToString("\n\n"))
            }

            append("\n\nPath: ")
            append(
                when {
                    internetNode.isConnected() -> "Internet"
                    directPeerCount > 0 -> "Local mesh"
                    else -> "Reconnecting"
                }
            )
            append(" • Auto reconnect ON")
        }

        AlertDialog.Builder(this)
            .setTitle("Riders • ${riderLines.size + 1} total")
            .setMessage(message)
            .setPositiveButton("INVITE") { _, _ -> showLiveInviteOptions() }
            .setNegativeButton("CLOSE", null)
            .show()
    }

    private fun showAudioRouteDialog() {
        val choices = arrayOf(
            "Auto — helmet if connected, otherwise phone",
            "Phone speaker + microphone",
            "Bluetooth helmet / headset",
        )
        val checked = when (binding.audioRoute.checkedRadioButtonId) {
            R.id.routePhone -> 1
            R.id.routeHelmet -> 2
            else -> 0
        }

        AlertDialog.Builder(this)
            .setTitle("Audio route • noise reduction ON")
            .setSingleChoiceItems(choices, checked) { dialog, which ->
                when (which) {
                    1 -> binding.routePhone.isChecked = true
                    2 -> binding.routeHelmet.isChecked = true
                    else -> binding.routeAuto.isChecked = true
                }
                applySelectedAudioRoute()
                saveSettings()
                dialog.dismiss()
            }
            .setNegativeButton("CANCEL", null)
            .show()
    }

    private fun transportModeLabel(): String = "INTERNET • WEBRTC OPUS"

    private fun showTransportModeDialog() {
        transportMode = TransportMode.INTERNET_ONLY
        meshLabRole = MeshNode.LabRole.NORMAL
        saveSettings()
        AlertDialog.Builder(this)
            .setTitle("Internet voice engine")
            .setMessage("Beta4 uses Internet-only WebRTC + Opus. Offline / multi-hop modes are not active in this package so voice stability can be tested independently.")
            .setPositiveButton("OK", null)
            .show()
    }

    private fun showMeshLabRoleDialog() {
        val choices = arrayOf(
            "NORMAL — normal riding group",
            "A — connects only to B",
            "B — relay between A and C",
            "C — connects only to B",
        )
        val checked = when (meshLabRole) {
            MeshNode.LabRole.NORMAL -> 0
            MeshNode.LabRole.A -> 1
            MeshNode.LabRole.B -> 2
            MeshNode.LabRole.C -> 3
        }
        AlertDialog.Builder(this)
            .setTitle("Offline multi-hop lab role")
            .setSingleChoiceItems(choices, checked) { dialog, which ->
                meshLabRole = when (which) {
                    1 -> MeshNode.LabRole.A
                    2 -> MeshNode.LabRole.B
                    3 -> MeshNode.LabRole.C
                    else -> MeshNode.LabRole.NORMAL
                }
                saveSettings()
                if (rideStarted && transportMode != TransportMode.INTERNET_ONLY) {
                    restartLocalMeshForRoleOrMode("lab role changed to ${meshLabRole.name}")
                    updateTransportStatus()
                    updateCapturePolicy()
                }
                dialog.dismiss()
            }
            .setNegativeButton("CANCEL", null)
            .show()
    }

    private fun applyTransportModeChange() {
        transportMode = TransportMode.INTERNET_ONLY
        meshLabRole = MeshNode.LabRole.NORMAL
        saveSettings()
        if (!rideStarted) return

        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        internetNode.stop()
        internetPeerCount = 0
        internetNode.start(normalizedRideCode(), rider, deviceLabel())
        internetNode.setMuted(micMuted)
        applySelectedAudioRoute()
        updateTransportStatus()
        updateCapturePolicy()
    }

    private fun showSettingsAndHelpDialog() {
        AlertDialog.Builder(this)
            .setTitle("RideMesh Beta4 settings & help")
            .setMessage(
                "Voice engine: WebRTC + Opus over Internet\n\n" +
                    "RideMesh automatically yields microphone and playback when a normal phone call, WhatsApp call or another VoIP app takes Android audio focus, then resumes after the call.\n\n" +
                    "Offline / multi-hop is intentionally disabled in this Beta4 package while we prioritize clear, stable group voice.\n\n" +
                    betaStatusSentence() + "\n\n" +
                    "Bug reports: WhatsApp group or direct support +91 9188664823."
            )
            .setPositiveButton("VOICE STATUS") { _, _ -> showRideStatusDialog() }
            .setNeutralButton("ENGINE INFO") { _, _ -> showTransportModeDialog() }
            .setNegativeButton("CLOSE", null)
            .show()
    }

    private fun ensureBetaFirstLaunch(): Long {
        val existing = prefs.getLong(BETA_FIRST_LAUNCH_KEY, 0L)
        if (existing > 0L) return existing
        val now = System.currentTimeMillis()
        prefs.edit().putLong(BETA_FIRST_LAUNCH_KEY, now).apply()
        return now
    }

    private fun betaFirstLaunchMs(): Long = ensureBetaFirstLaunch()

    private fun betaRemainingDays(nowMs: Long = System.currentTimeMillis()): Long =
        BetaWindow.remainingDays(betaFirstLaunchMs(), nowMs)

    private fun isBetaExpired(nowMs: Long = System.currentTimeMillis()): Boolean =
        BetaWindow.isExpired(betaFirstLaunchMs(), nowMs)

    private fun betaStatusSentence(): String {
        val days = betaRemainingDays()
        return if (days <= 0L) {
            "Beta access: expired"
        } else {
            "Beta access: $days day${if (days == 1L) "" else "s"} remaining"
        }
    }

    private fun refreshBetaAccessUi(showWarning: Boolean) {
        val days = betaRemainingDays()
        val expired = days <= 0L
        binding.betaExpiryStatus.text = if (expired) {
            "BETA PERIOD ENDED • UPDATE REQUIRED"
        } else {
            "BETA ACCESS • $days DAY${if (days == 1L) "" else "S"} REMAINING"
        }
        binding.betaExpiryStatus.setTextColor(
            ContextCompat.getColor(this, if (expired || days <= 3L) R.color.danger else if (days <= 14L) R.color.amber else R.color.accent)
        )
        binding.createRide.isEnabled = !expired
        binding.joinRide.isEnabled = !expired
        binding.startRide.isEnabled = !expired
        binding.findNearby.isEnabled = !expired

        if (expired) {
            showBetaExpiredDialog()
        } else if (showWarning) {
            maybeShowBetaWarning(days)
        }
    }

    private fun ensureBetaUsable(): Boolean {
        if (!isBetaExpired()) return true
        refreshBetaAccessUi(showWarning = false)
        return false
    }

    private fun maybeShowBetaWarning(days: Long) {
        val bucket = BetaWindow.warningBucket(days) ?: return
        val lastBucket = prefs.getInt(BETA_WARNING_BUCKET_KEY, 0)
        if (lastBucket == bucket) return
        prefs.edit().putInt(BETA_WARNING_BUCKET_KEY, bucket).apply()
        AlertDialog.Builder(this)
            .setTitle("RideMesh Beta • $days day${if (days == 1L) "" else "s"} left")
            .setMessage("This tester build expires 60 days after its first launch. Install the latest RideMesh build before the timer reaches zero.")
            .setPositiveButton("OK", null)
            .show()
    }

    private fun showBetaExpiredDialog() {
        if (betaExpiredDialogShown || isFinishing || isDestroyed) return
        betaExpiredDialogShown = true
        AlertDialog.Builder(this)
            .setTitle("BETA PERIOD ENDED")
            .setMessage("This RideMesh Beta build has reached its 60-day test limit. Ride creation and joining are disabled. Please install the latest RideMesh version.")
            .setPositiveButton("OK", null)
            .setOnDismissListener { betaExpiredDialogShown = false }
            .show()
    }

    private fun expireActiveRide() {
        if (!rideStarted) {
            refreshBetaAccessUi(showWarning = false)
            return
        }
        stopRide()
        showBetaExpiredDialog()
    }

    private fun showOfflineDiagnosticsDialog() {
        showRideStatusDialog()
    }

    private fun showRideStatusDialog() {
        val diag = internetNode.diagnostics()
        AlertDialog.Builder(this)
            .setTitle("Ride status • WebRTC + Opus")
            .setMessage(
                "Path: Internet WebRTC\n" +
                    "Codec: ${diag.codec}\n" +
                    "Signaling: ${if (diag.signalingConnected) "CONNECTED" else "RECONNECTING"}\n" +
                    "Known riders: ${diag.knownRiders + 1}\n" +
                    "Voice peers connected: ${diag.voicePeersConnected}\n" +
                    "SDP offers sent: ${diag.offersSent} • answers: ${diag.answersSent}\n" +
                    "ICE candidates sent: ${diag.candidatesSent}\n" +
                    "ICE reconnects: ${diag.reconnects}\n" +
                    "TURN relay: ${if (diag.turnConfigured) "CONFIGURED" else "NOT CONFIGURED IN THIS BETA"}\n" +
                    "Last network error: ${diag.lastError.ifBlank { "none" }}\n\n" +
                    "PEER STATES\n${diag.peerStates}\n\n" +
                    "Audio: ${binding.audioTile.text}\n" +
                    "Microphone: ${if (micMuted) "MUTED" else "LIVE"}\n" +
                    "Call-safe audio focus: ON\n" +
                    betaStatusSentence()
            )
            .setPositiveButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }
            .setNegativeButton("CLOSE", null)
            .show()
    }

    private fun openWhatsAppBugReport() {
        val options = arrayOf(
            "Join RideMesh bug report group",
            "Send direct WhatsApp report to +91 9188664823",
        )
        AlertDialog.Builder(this)
            .setTitle("Report a RideMesh bug")
            .setItems(options) { _, which ->
                if (which == 0) {
                    openExternalUri(BUG_REPORT_GROUP_URL, "Could not open the RideMesh bug report group")
                } else {
                    openDirectWhatsAppBugReport()
                }
            }
            .setNegativeButton("CLOSE", null)
            .show()
    }

    private fun openDirectWhatsAppBugReport() {
        val message = buildString {
            append("RideMesh bug report\n")
            append("Ride code: ${normalizedRideCode()}\n")
            append("Phone: ${Build.MANUFACTURER} ${Build.MODEL}\n")
            append("Android: ${Build.VERSION.RELEASE}\n")
            append("Current path: ${if (rideStarted) binding.networkTile.text else "Not riding"}\n")
            append("Voice engine: WebRTC + Opus\n")
            if (::internetNode.isInitialized) {
                val d = internetNode.diagnostics()
                append("WebRTC: signaling=${d.signalingConnected}, voicePeers=${d.voicePeersConnected}, riders=${d.knownRiders}, offers=${d.offersSent}, answers=${d.answersSent}, iceCandidates=${d.candidatesSent}, reconnects=${d.reconnects}, TURN=${d.turnConfigured}, error=${d.lastError.ifBlank { "none" }}\n")
                append("Peer states: ${d.peerStates.replace('\n', ';')}\n")
            }
            append("Problem: ")
        }
        val url = "https://wa.me/$SUPPORT_WHATSAPP?text=${Uri.encode(message)}"
        openExternalUri(url, "Could not open WhatsApp bug report")
    }

    private fun openRideMeshCommunity() {
        openExternalUri(COMMUNITY_URL, "Could not open RideMesh community link")
    }

    private fun openExternalUri(url: String, failureMessage: String) {
        try {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
        } catch (_: ActivityNotFoundException) {
            AlertDialog.Builder(this)
                .setTitle("Link unavailable")
                .setMessage(failureMessage)
                .setPositiveButton("OK", null)
                .show()
        } catch (_: Throwable) {
            AlertDialog.Builder(this)
                .setTitle("Link unavailable")
                .setMessage(failureMessage)
                .setPositiveButton("OK", null)
                .show()
        }
    }

    private fun clearNearbyRiders(message: String) {
        nearbyButtons.clear()
        binding.nearbyUsers.removeAllViews()
        val text = android.widget.TextView(this).apply {
            this.text = message
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
            textSize = 12f
            setPadding(4, 10, 4, 10)
        }
        binding.nearbyUsers.addView(text)
    }

    private fun log(message: String) {
        val stamp = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())
        val old = binding.logView.text?.toString().orEmpty()
        binding.logView.text = "$stamp  $message\n$old".take(7000)
    }

    override fun onDestroy() {
        saveSettings()
        mainHandler.removeCallbacks(stopLobbyScan)
        mainHandler.removeCallbacks(rideWatchdog)
        if (::lobbyNode.isInitialized) lobbyNode.stop()
        if (::internetNode.isInitialized && !rideStarted) internetNode.stop()
        if (!rideStarted && ::audioEngine.isInitialized) audioEngine.release()
        super.onDestroy()
    }

    companion object {
        private const val SELF_TILE_KEY = "self"
        private const val MAX_VISIBLE_RIDER_TILES = 6
        private const val SPEAKING_HOLD_MS = 560L
        private const val LOBBY_SCAN_WINDOW_MS = 20_000L
        private const val WATCHDOG_INTERVAL_MS = 5_000L
        private const val INTERNET_STABLE_BEFORE_MESH_SLEEP_MS = 15_000L
        private const val LOCAL_MESH_REFRESH_MS = 8_000L
        private const val LOCAL_MESH_RESTART_SETTLE_MS = 700L
        private const val BETA_FIRST_LAUNCH_KEY = "beta_first_launch_ms_v2"
        private const val BETA_WARNING_BUCKET_KEY = "beta_warning_bucket_v2"
        private const val SUPPORT_WHATSAPP = "919188664823"
        private const val BUG_REPORT_GROUP_URL = "https://chat.whatsapp.com/CGToJCBDG6XFGUpeTp7uKW"
        private const val COMMUNITY_URL = "https://chat.whatsapp.com/GTH7FA1uTUFGRXElnfDfdE"
    }
}
