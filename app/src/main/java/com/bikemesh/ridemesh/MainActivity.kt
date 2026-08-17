package com.bikemesh.ridemesh

import android.Manifest
import android.app.AlertDialog
import android.bluetooth.BluetoothManager
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.ImageView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.bikemesh.ridemesh.audio.AudioEngine
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
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
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

    private var rideStarted = false
    private var pttPressed = false
    private var pendingAction = PendingAction.NONE
    private var directPeerCount = 0
    private var meshRunning = false

    private enum class PendingAction { NONE, START_RIDE, FIND_RIDERS }
    private enum class Screen { HOME, SETUP, ACTIVE }

    private val stopLobbyScan = Runnable {
        if (!rideStarted) {
            lobbyNode.stop()
            binding.findNearby.text = "FIND NEARBY RIDEMESH RIDERS"
            log("Nearby scan paused after 30 seconds to save battery. Tap FIND to scan again.")
        }
    }

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        if (!hasRequiredPermissions()) {
            log("Required Nearby/Bluetooth/microphone permission was denied")
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
        meshNode = MeshNode(applicationContext, this)
        lobbyNode = LobbyNode(applicationContext, this)
        internetNode = InternetNode(this)
        audioEngine = AudioEngine(
            context = applicationContext,
            onCapturedFrame = ::sendHybridAudio,
            onStatus = { text -> runOnUiThread { updateAudioUi(text) } },
        )

        applySelectedAudioRoute()
        updateModeUi()
        showScreen(Screen.HOME)
        clearNearbyRiders("Tap FIND to discover RideMesh riders nearby.")

        binding.createRide.setOnClickListener {
            binding.setupTitle.text = "CREATE RIDE"
            binding.rideCode.setText(generateRideCode())
            showScreen(Screen.SETUP)
        }
        binding.joinRide.setOnClickListener {
            binding.setupTitle.text = "JOIN RIDE"
            showScreen(Screen.SETUP)
            binding.rideCode.requestFocus()
        }
        binding.backHome.setOnClickListener {
            stopLobbyDiscovery()
            showScreen(Screen.HOME)
        }
        binding.openSettings.setOnClickListener { showSettingsDialog() }
        binding.activeSettings.setOnClickListener { showRideStatusDialog() }
        binding.activeBluetooth.setOnClickListener { showBluetoothDialog() }
        binding.activeNetwork.setOnClickListener { showNetworkDialog() }
        binding.activeSos.setOnClickListener { showSosDialog() }
        binding.activeStop.setOnClickListener { stopRide() }

        binding.audioRoute.setOnCheckedChangeListener { _, _ ->
            applySelectedAudioRoute()
            saveSettings()
        }
        binding.batterySaver.setOnCheckedChangeListener { _, _ ->
            saveSettings()
            applyBatteryPolicy()
        }
        binding.hardwarePtt.setOnCheckedChangeListener { _, _ -> saveSettings() }
        binding.labRole.setOnCheckedChangeListener { _, _ ->
            updateModeUi()
            saveSettings()
        }
        binding.startRide.setOnClickListener {
            if (rideStarted) stopRide() else ensurePermissionsAndRun(PendingAction.START_RIDE)
        }
        binding.findNearby.setOnClickListener {
            if (rideStarted) log("Stop the active ride before using the pre-ride nearby invitation list")
            else ensurePermissionsAndRun(PendingAction.FIND_RIDERS)
        }
        binding.showQr.setOnClickListener { showRideQr() }
        binding.scanQr.setOnClickListener { scanRideQr() }
        binding.ptt.setOnTouchListener { _, event ->
            if (!isBenchPttMode() || !rideStarted) return@setOnTouchListener true
            when (event.action) {
                MotionEvent.ACTION_DOWN -> setPtt(true)
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> setPtt(false)
            }
            true
        }
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        if (rideStarted && isBenchPttMode() && binding.hardwarePtt.isChecked && isVolumeKey(keyCode)) {
            if (event?.repeatCount == 0) setPtt(true)
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (rideStarted && isBenchPttMode() && binding.hardwarePtt.isChecked && isVolumeKey(keyCode)) {
            setPtt(false)
            return true
        }
        return super.onKeyUp(keyCode, event)
    }

    private fun showScreen(screen: Screen) {
        binding.screenHome.visibility = if (screen == Screen.HOME) View.VISIBLE else View.GONE
        binding.screenSetup.visibility = if (screen == Screen.SETUP) View.VISIBLE else View.GONE
        binding.screenActive.visibility = if (screen == Screen.ACTIVE) View.VISIBLE else View.GONE
    }

    private fun setPtt(active: Boolean): Boolean {
        if (!rideStarted || !isBenchPttMode() || pttPressed == active) return true
        pttPressed = active
        if (active) {
            binding.ptt.text = "TRANSMITTING"
            audioEngine.startTransmit()
        } else {
            binding.ptt.text = "BENCH TALK"
            audioEngine.stopTransmit()
        }
        return true
    }

    private fun ensurePermissionsAndRun(action: PendingAction) {
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

    private fun startNearbyLobby() {
        if (!radiosReady()) {
            log("Nearby riders unavailable: turn ON Bluetooth and Wi-Fi, then tap FIND again")
            return
        }
        stopLobbyDiscovery()
        clearNearbyRiders("Scanning… other RideMesh phones should tap FIND too.")
        lobbyNode.start(binding.riderName.text?.toString().orEmpty(), binding.rideCode.text?.toString().orEmpty())
        binding.findNearby.text = "SCANNING NEARBY RIDERS…"
        mainHandler.postDelayed(stopLobbyScan, LOBBY_SCAN_WINDOW_MS)
        log("Battery-smart nearby scan started for 30 seconds")
    }

    private fun stopLobbyDiscovery() {
        mainHandler.removeCallbacks(stopLobbyScan)
        if (::lobbyNode.isInitialized) lobbyNode.stop()
        if (::binding.isInitialized) binding.findNearby.text = "FIND NEARBY RIDEMESH RIDERS"
    }

    private fun showRideQr() {
        val code = normalizedRideCode()
        binding.rideCode.setText(code)
        saveSettings()
        val payload = "ridemesh://join?ride=${Uri.encode(code)}"
        try {
            val size = 720
            val matrix = QRCodeWriter().encode(payload, BarcodeFormat.QR_CODE, size, size)
            val bitmap = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888)
            for (y in 0 until size) for (x in 0 until size) {
                bitmap.setPixel(x, y, if (matrix[x, y]) Color.BLACK else Color.WHITE)
            }
            val image = ImageView(this).apply {
                setImageBitmap(bitmap)
                adjustViewBounds = true
                setPadding(24, 24, 24, 24)
            }
            AlertDialog.Builder(this)
                .setTitle("Join $code")
                .setMessage("Other riders: RideMesh → JOIN RIDE → SCAN QR")
                .setView(image)
                .setPositiveButton("DONE", null)
                .show()
            log("Showing join QR for $code")
        } catch (t: Throwable) {
            log("Could not create QR: ${t.message ?: t.javaClass.simpleName}")
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
                    log("That QR is not a RideMesh join code")
                    return@addOnSuccessListener
                }
                binding.rideCode.setText(code)
                saveSettings()
                log("QR accepted • ready to join $code")
                AlertDialog.Builder(this)
                    .setTitle("RideMesh invite")
                    .setMessage("Ride code $code loaded. Join now?")
                    .setNegativeButton("LATER", null)
                    .setPositiveButton("JOIN") { _, _ -> ensurePermissionsAndRun(PendingAction.START_RIDE) }
                    .show()
            }
            .addOnCanceledListener { log("QR scan cancelled") }
            .addOnFailureListener { log("QR scanner error: ${it.message ?: "unknown"}") }
    }

    private fun parseRideQr(raw: String): String? = runCatching {
        val uri = Uri.parse(raw)
        if (!uri.scheme.equals("ridemesh", true) || !uri.host.equals("join", true)) return@runCatching null
        uri.getQueryParameter("ride")?.trim()?.uppercase()?.takeIf { it.isNotBlank() }?.take(12)
    }.getOrNull()

    private fun startRideNow() {
        if (rideStarted) return
        val rider = binding.riderName.text?.toString().orEmpty()
        val code = normalizedRideCode()
        binding.rideCode.setText(code)
        saveSettings()

        try {
            stopLobbyDiscovery()
            startRideServiceSafely()
            rideStarted = true
            directPeerCount = 0
            meshRunning = false
            applySelectedAudioRoute()
            audioEngine.selectCommunicationDevice()

            if (isBenchPttMode()) {
                ensureLocalMeshRunning("bench topology")
                log("Bench ride started • local mesh only • hold BENCH TALK to transmit")
            } else {
                internetNode.start(code)
                ensureLocalMeshRunning("initial hybrid fallback")
                log("Ride started • hands-free hybrid mode")
            }

            binding.activeRideCode.text = code
            binding.startRide.text = "STOP RIDE"
            showScreen(Screen.ACTIVE)
            updateModeUi()
            updateTransportStatus()
            updateCapturePolicy()
        } catch (t: Throwable) {
            recoverFromStartFailure(t)
        }
    }

    private fun sendHybridAudio(audio: ByteArray) {
        if (!rideStarted || audio.isEmpty()) return
        if (isBenchPttMode()) {
            meshNode.sendLocalAudio(audio)
            return
        }
        if (internetNode.isConnected()) {
            if (!internetNode.sendLocalAudio(audio)) meshNode.sendLocalAudio(audio)
        } else meshNode.sendLocalAudio(audio)
    }

    private fun ensureLocalMeshRunning(reason: String) {
        if (!rideStarted || meshRunning || !radiosReady()) return
        meshNode.start(binding.riderName.text?.toString().orEmpty(), normalizedRideCode(), selectedLabRole())
        meshRunning = true
        log("Local mesh awake • $reason")
    }

    private fun sleepLocalMesh(reason: String) {
        if (!meshRunning) return
        meshRunning = false
        meshNode.stop()
        directPeerCount = 0
        log("Local mesh sleeping • $reason")
    }

    private fun applyBatteryPolicy() {
        applyBatteryPolicyUiOnly()
        if (!rideStarted || isBenchPttMode()) return
        if (binding.batterySaver.isChecked && internetNode.isConnected()) {
            sleepLocalMesh("Internet stable — battery smart mode")
        } else {
            ensureLocalMeshRunning(if (internetNode.isConnected()) "Battery Smart disabled" else "Internet unavailable")
        }
        updateTransportStatus()
        updateCapturePolicy()
    }

    private fun updateCapturePolicy() {
        if (!rideStarted || isBenchPttMode()) return
        if (internetNode.isConnected() || directPeerCount > 0) audioEngine.startTransmit()
        else {
            audioEngine.stopTransmit()
            updateAudioUi("Waiting for connection • mic sleeping")
        }
    }

    private fun startRideServiceSafely() {
        try {
            ContextCompat.startForegroundService(this, Intent(this, RideService::class.java))
        } catch (t: Throwable) {
            log("Background ride service unavailable: ${t.javaClass.simpleName}. Continuing while app is open.")
        }
    }

    private fun recoverFromStartFailure(t: Throwable) {
        runCatching { audioEngine.stopTransmit() }
        runCatching { internetNode.stop() }
        runCatching { meshNode.stop() }
        runCatching { stopService(Intent(this, RideService::class.java)) }
        rideStarted = false
        meshRunning = false
        pttPressed = false
        directPeerCount = 0
        binding.startRide.text = "START / JOIN RIDE"
        log("START ERROR — ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")
        showScreen(Screen.SETUP)
    }

    private fun radiosReady(): Boolean {
        val bluetoothOn = try { getSystemService(BluetoothManager::class.java).adapter?.isEnabled == true } catch (_: Throwable) { false }
        val wifiOn = try { applicationContext.getSystemService(WifiManager::class.java).isWifiEnabled } catch (_: Throwable) { false }
        return bluetoothOn && wifiOn
    }

    private fun stopRide() {
        if (!rideStarted) {
            showScreen(Screen.HOME)
            return
        }
        if (isBenchPttMode()) setPtt(false)
        audioEngine.stopTransmit()
        internetNode.stop()
        meshRunning = false
        meshNode.stop()
        stopService(Intent(this, RideService::class.java))
        rideStarted = false
        pttPressed = false
        directPeerCount = 0
        binding.startRide.text = "START / JOIN RIDE"
        binding.riderCount.text = "0 RIDERS CONNECTED"
        binding.meshStatus.text = "HYBRID: STOPPED"
        binding.networkTile.text = "OFFLINE"
        binding.homeNetworkStatus.text = "●  Hybrid network ready"
        log("Ride stopped")
        showScreen(Screen.HOME)
    }

    private fun updateModeUi() {
        val bench = isBenchPttMode()
        binding.hardwarePtt.visibility = if (bench) View.VISIBLE else View.GONE
        binding.handsFreeIndicator.visibility = if (bench) View.GONE else View.VISIBLE
        binding.benchTalkContainer.visibility = if (bench) View.VISIBLE else View.GONE
        if (!bench) binding.ptt.text = "BENCH TALK"
    }

    private fun isBenchPttMode(): Boolean = selectedLabRole() != MeshNode.LabRole.NORMAL

    private fun applySelectedAudioRoute() {
        if (!::audioEngine.isInitialized) return
        val route = when (binding.audioRoute.checkedRadioButtonId) {
            R.id.routePhone -> AudioRoute.PHONE
            R.id.routeHelmet -> AudioRoute.HELMET
            else -> AudioRoute.AUTO
        }
        audioEngine.setRoute(route)
        if (rideStarted) updateAudioUi(audioEngine.selectCommunicationDevice())
    }

    private fun updateAudioUi(text: String) {
        binding.audioStatus.text = text
        binding.homeAudioStatus.text = text
        binding.audioTile.text = when {
            text.contains("Bluetooth", true) || text.contains("headset", true) -> "HELMET"
            text.contains("sleep", true) || text.contains("Waiting", true) -> "SLEEP"
            else -> "PHONE"
        }
    }

    private fun restoreSettings() {
        binding.riderName.setText(prefs.getString("rider", Build.MODEL.take(18)))
        binding.rideCode.setText(prefs.getString("code", "RIDE01"))
        binding.hardwarePtt.isChecked = prefs.getBoolean("hardware_ptt", false)
        binding.batterySaver.isChecked = prefs.getBoolean("battery_smart", true)
        when (prefs.getString("lab_role", "NORMAL")) {
            "A" -> binding.labA.isChecked = true
            "B" -> binding.labB.isChecked = true
            "C" -> binding.labC.isChecked = true
            else -> binding.labNormal.isChecked = true
        }
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
            .putString("lab_role", selectedLabRole().name)
            .putBoolean("hardware_ptt", binding.hardwarePtt.isChecked)
            .putBoolean("battery_smart", binding.batterySaver.isChecked)
            .apply()
    }

    private fun normalizedRideCode(): String = binding.rideCode.text?.toString().orEmpty().trim().uppercase().ifBlank { "RIDE01" }.take(12)
    private fun generateRideCode(): String = "RM" + Random.nextInt(1000, 9999)

    private fun selectedLabRole(): MeshNode.LabRole = when (binding.labRole.checkedRadioButtonId) {
        R.id.labA -> MeshNode.LabRole.A
        R.id.labB -> MeshNode.LabRole.B
        R.id.labC -> MeshNode.LabRole.C
        else -> MeshNode.LabRole.NORMAL
    }

    private fun hasRequiredPermissions(): Boolean = requiredPermissions().all {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun requiredPermissions(): List<String> = buildList {
        add(Manifest.permission.RECORD_AUDIO)
        when {
            Build.VERSION.SDK_INT >= 33 -> {
                add(Manifest.permission.BLUETOOTH_SCAN)
                add(Manifest.permission.BLUETOOTH_CONNECT)
                add(Manifest.permission.BLUETOOTH_ADVERTISE)
                add(Manifest.permission.NEARBY_WIFI_DEVICES)
            }
            Build.VERSION.SDK_INT >= 31 -> {
                add(Manifest.permission.BLUETOOTH_SCAN)
                add(Manifest.permission.BLUETOOTH_CONNECT)
                add(Manifest.permission.BLUETOOTH_ADVERTISE)
                add(Manifest.permission.ACCESS_FINE_LOCATION)
            }
            Build.VERSION.SDK_INT >= 29 -> add(Manifest.permission.ACCESS_FINE_LOCATION)
            else -> add(Manifest.permission.ACCESS_COARSE_LOCATION)
        }
    }

    override fun onLog(message: String) { runOnUiThread { log(message) } }

    override fun onDirectPeerCount(count: Int) {
        directPeerCount = count
        runOnUiThread {
            updateTransportStatus()
            updateCapturePolicy()
        }
    }

    override fun onAudioPacket(audio: ByteArray) {
        if (rideStarted) audioEngine.playIncoming(audio)
    }

    override fun onInternetState(connected: Boolean, message: String) {
        runOnUiThread {
            log(message)
            if (rideStarted && !isBenchPttMode()) {
                if (connected && binding.batterySaver.isChecked) sleepLocalMesh("Internet stable — automatic battery saving")
                else if (!connected) ensureLocalMeshRunning("Internet path lost")
                else ensureLocalMeshRunning("parallel local standby requested")
            }
            updateTransportStatus()
            updateCapturePolicy()
        }
    }

    override fun onInternetAudio(audio: ByteArray) {
        if (rideStarted && !isBenchPttMode()) audioEngine.playIncoming(audio)
    }

    private fun updateTransportStatus() {
        if (!rideStarted) return
        when {
            isBenchPttMode() -> {
                binding.networkTile.text = "LOCAL"
                binding.meshStatus.text = "BENCH MESH • $directPeerCount DIRECT PEERS"
                binding.riderCount.text = "${directPeerCount + 1} LOCAL RIDERS"
            }
            internetNode.isConnected() -> {
                binding.networkTile.text = "INTERNET"
                binding.meshStatus.text = if (binding.batterySaver.isChecked) "INTERNET ACTIVE • LOCAL MESH SLEEPING" else "INTERNET ACTIVE • LOCAL MESH STANDBY"
                binding.riderCount.text = "INTERNET GROUP ACTIVE"
            }
            directPeerCount > 0 -> {
                binding.networkTile.text = "LOCAL MESH"
                binding.meshStatus.text = "OFFLINE MESH ACTIVE • $directPeerCount DIRECT PEERS"
                binding.riderCount.text = "${directPeerCount + 1} LOCAL RIDERS"
            }
            else -> {
                binding.networkTile.text = "RECONNECT"
                binding.meshStatus.text = "SEARCHING FOR INTERNET OR LOCAL RIDERS"
                binding.riderCount.text = "WAITING FOR RIDERS"
            }
        }
        binding.homeNetworkStatus.text = when {
            internetNode.isConnected() -> "●  Internet voice active"
            directPeerCount > 0 -> "●  Local mesh active"
            else -> "●  Hybrid network ready"
        }
        applyBatteryPolicyUiOnly()
    }

    private fun applyBatteryPolicyUiOnly() {
        binding.powerTile.text = if (binding.batterySaver.isChecked) "SMART" else "MAX LINK"
        binding.powerTile.setTextColor(ContextCompat.getColor(this, if (binding.batterySaver.isChecked) R.color.green else R.color.amber))
    }

    override fun onLobbyLog(message: String) { runOnUiThread { log(message) } }

    override fun onNearbyRiderFound(endpointId: String, riderName: String, rideCode: String) {
        runOnUiThread {
            if (nearbyButtons.containsKey(endpointId)) return@runOnUiThread
            if (nearbyButtons.isEmpty()) binding.nearbyUsers.removeAllViews()
            val button = MaterialButton(this).apply {
                isAllCaps = false
                text = "$riderName  •  $rideCode     INVITE"
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
                strokeColor = ContextCompat.getColorStateList(this@MainActivity, R.color.border)
                setOnClickListener {
                    lobbyNode.invite(endpointId, normalizedRideCode(), binding.riderName.text?.toString().orEmpty())
                }
            }
            nearbyButtons[endpointId] = button
            binding.nearbyUsers.addView(button)
            log("Nearby RideMesh rider found: $riderName")
        }
    }

    override fun onNearbyRiderLost(endpointId: String) {
        runOnUiThread {
            val button = nearbyButtons.remove(endpointId) ?: return@runOnUiThread
            binding.nearbyUsers.removeView(button)
            if (nearbyButtons.isEmpty()) clearNearbyRiders("No RideMesh riders visible yet. Tap FIND to scan again.")
        }
    }

    override fun onRideInviteReceived(inviterName: String, rideCode: String) {
        runOnUiThread {
            AlertDialog.Builder(this)
                .setTitle("RideMesh invitation")
                .setMessage("$inviterName invited you to ride $rideCode")
                .setNegativeButton("DECLINE", null)
                .setPositiveButton("JOIN RIDE") { _, _ ->
                    binding.rideCode.setText(rideCode)
                    saveSettings()
                    stopLobbyDiscovery()
                    ensurePermissionsAndRun(PendingAction.START_RIDE)
                }
                .show()
        }
    }

    private fun showSettingsDialog() {
        AlertDialog.Builder(this)
            .setTitle("RideMesh settings")
            .setMessage("Battery Smart: ${if (binding.batterySaver.isChecked) "ON" else "OFF"}\n\nBattery Smart pauses local mesh radios while Internet voice is stable, wakes mesh automatically when Internet fails, suppresses silence with VAD, and limits nearby discovery scans to 30 seconds.\n\nChange audio route and Battery Smart Mode in the Ride Lobby.")
            .setPositiveButton("OK", null)
            .show()
    }

    private fun showRideStatusDialog() {
        AlertDialog.Builder(this)
            .setTitle("Ride status")
            .setMessage("${binding.meshStatus.text}\n${binding.riderCount.text}\n${binding.audioStatus.text}\nPower: ${binding.powerTile.text}")
            .setPositiveButton("OK", null)
            .show()
    }

    private fun showBluetoothDialog() {
        val route = audioEngine.selectCommunicationDevice()
        updateAudioUi(route)
        AlertDialog.Builder(this)
            .setTitle("Bluetooth / audio")
            .setMessage("$route\n\nRideMesh uses the helmet only as the phone's microphone and speaker. Intercom brand-to-brand compatibility is not required.")
            .setPositiveButton("OK", null)
            .show()
    }

    private fun showNetworkDialog() {
        val path = when {
            isBenchPttMode() -> "Local bench mesh"
            internetNode.isConnected() -> "Internet relay (preferred)"
            directPeerCount > 0 -> "Nearby local mesh"
            else -> "Reconnecting"
        }
        AlertDialog.Builder(this)
            .setTitle("Network status")
            .setMessage("Active path: $path\nDirect local peers: $directPeerCount\nBattery Smart: ${if (binding.batterySaver.isChecked) "ON" else "OFF"}\n\nInternet relay in this test build is experimental. Production will use an authenticated RideMesh service.")
            .setPositiveButton("OK", null)
            .show()
    }

    private fun showSosDialog() {
        AlertDialog.Builder(this)
            .setTitle("SOS")
            .setMessage("SOS is visible in the new riding UI, but GPS emergency broadcasting is not enabled in this prototype yet. Do not rely on this button for emergency services.")
            .setPositiveButton("UNDERSTOOD", null)
            .show()
    }

    private fun clearNearbyRiders(message: String) {
        nearbyButtons.clear()
        binding.nearbyUsers.removeAllViews()
        val text = android.widget.TextView(this).apply {
            this.text = message
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
            textSize = 12f
            setPadding(4, 8, 4, 8)
        }
        binding.nearbyUsers.addView(text)
    }

    private fun log(message: String) {
        val stamp = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())
        val old = binding.logView.text?.toString().orEmpty()
        binding.logView.text = "$stamp  $message\n$old".take(7000)
    }

    private fun isVolumeKey(keyCode: Int): Boolean = keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN

    override fun onDestroy() {
        saveSettings()
        mainHandler.removeCallbacks(stopLobbyScan)
        if (::lobbyNode.isInitialized) lobbyNode.stop()
        if (::internetNode.isInitialized && !rideStarted) internetNode.stop()
        if (!rideStarted && ::audioEngine.isInitialized) audioEngine.release()
        super.onDestroy()
    }

    companion object {
        private const val LOBBY_SCAN_WINDOW_MS = 30_000L
    }
}