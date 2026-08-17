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
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
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

class MainActivity : AppCompatActivity(), MeshNode.Listener, LobbyNode.Listener, InternetNode.Listener {
    private lateinit var binding: ActivityMainBinding
    private lateinit var meshNode: MeshNode
    private lateinit var lobbyNode: LobbyNode
    private lateinit var internetNode: InternetNode
    private lateinit var audioEngine: AudioEngine
    private val prefs by lazy { getSharedPreferences("ridemesh", MODE_PRIVATE) }
    private val nearbyButtons = linkedMapOf<String, MaterialButton>()

    private var rideStarted = false
    private var pttPressed = false
    private var pendingAction = PendingAction.NONE
    private var directPeerCount = 0

    private enum class PendingAction { NONE, START_RIDE, FIND_RIDERS }

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

        restoreSettings()

        meshNode = MeshNode(applicationContext, this)
        lobbyNode = LobbyNode(applicationContext, this)
        internetNode = InternetNode(this)
        audioEngine = AudioEngine(
            context = applicationContext,
            onCapturedFrame = ::sendHybridAudio,
            onStatus = { text -> runOnUiThread { binding.audioStatus.text = text } },
        )
        applySelectedAudioRoute()
        updateModeUi()

        binding.audioRoute.setOnCheckedChangeListener { _, _ ->
            applySelectedAudioRoute()
            saveSettings()
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
            if (rideStarted) {
                log("Stop the active ride before using the pre-ride nearby invitation list")
            } else {
                ensurePermissionsAndRun(PendingAction.FIND_RIDERS)
            }
        }

        binding.showQr.setOnClickListener { showRideQr() }
        binding.scanQr.setOnClickListener { scanRideQr() }

        binding.ptt.setOnTouchListener { _, event ->
            if (!isBenchPttMode()) return@setOnTouchListener true
            if (!rideStarted) {
                if (event.action == MotionEvent.ACTION_DOWN) log("Start / join a ride first")
                return@setOnTouchListener true
            }
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

        clearNearbyRiders("Searching… other RideMesh phones should tap FIND NEARBY RIDEMESH RIDERS too.")
        lobbyNode.start(
            binding.riderName.text?.toString().orEmpty(),
            binding.rideCode.text?.toString().orEmpty(),
        )
        binding.findNearby.text = "REFRESH NEARBY RIDERS"
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
            for (y in 0 until size) {
                for (x in 0 until size) {
                    bitmap.setPixel(x, y, if (matrix[x, y]) Color.BLACK else Color.WHITE)
                }
            }

            val image = ImageView(this).apply {
                setImageBitmap(bitmap)
                adjustViewBounds = true
                setPadding(24, 24, 24, 24)
            }
            AlertDialog.Builder(this)
                .setTitle("Join $code")
                .setMessage("Other riders: RideMesh → SCAN QR")
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
        val scanner = GmsBarcodeScanning.getClient(this, options)
        scanner.startScan()
            .addOnSuccessListener { barcode ->
                val raw = barcode.rawValue.orEmpty()
                val code = parseRideQr(raw)
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

    private fun parseRideQr(raw: String): String? {
        return runCatching {
            val uri = Uri.parse(raw)
            if (!uri.scheme.equals("ridemesh", true) || !uri.host.equals("join", true)) return@runCatching null
            uri.getQueryParameter("ride")?.trim()?.uppercase()?.takeIf { it.isNotBlank() }?.take(12)
        }.getOrNull()
    }

    private fun startRideNow() {
        if (rideStarted) return

        val rider = binding.riderName.text?.toString().orEmpty()
        val code = normalizedRideCode()
        binding.rideCode.setText(code)
        saveSettings()

        try {
            lobbyNode.stop()
            clearNearbyRiders("Ride active. Stop ride to search/invite nearby riders.")
            startRideServiceSafely()

            rideStarted = true
            directPeerCount = 0
            applySelectedAudioRoute()
            audioEngine.selectCommunicationDevice()

            // Internet is preferred. The public relay is experimental test infrastructure.
            internetNode.start(code)

            // Keep Nearby alive as the automatic no-coverage fallback whenever radios are available.
            if (radiosReady()) {
                meshNode.start(rider, code, selectedLabRole())
            } else {
                log("Local mesh standby unavailable because Bluetooth/Wi-Fi is off. Internet voice can still connect.")
            }

            binding.startRide.text = "STOP RIDE"
            binding.meshStatus.text = "Hybrid: connecting Internet • mesh standby"
            binding.findNearby.isEnabled = false
            binding.showQr.isEnabled = false
            binding.scanQr.isEnabled = false

            if (isBenchPttMode()) {
                log("Bench ride started. Hold BENCH TALK (or a volume key if enabled) to transmit.")
            } else {
                audioEngine.startTransmit()
                log("Ride started • HYBRID HANDS-FREE • Internet preferred, Nearby fallback.")
            }
        } catch (t: Throwable) {
            recoverFromStartFailure(t)
        }
    }

    private fun sendHybridAudio(audio: ByteArray) {
        if (!rideStarted || audio.isEmpty()) return

        // Prefer the long-range Internet path. If publish fails or Internet is unavailable,
        // immediately use the Nearby mesh path instead.
        if (internetNode.isConnected()) {
            if (!internetNode.sendLocalAudio(audio)) meshNode.sendLocalAudio(audio)
        } else {
            meshNode.sendLocalAudio(audio)
        }
    }

    private fun startRideServiceSafely() {
        try {
            ContextCompat.startForegroundService(this, Intent(this, RideService::class.java))
        } catch (t: Throwable) {
            log("Background ride service unavailable: ${t.javaClass.simpleName}: ${t.message ?: "unknown"}. Continuing while app is open.")
        }
    }

    private fun recoverFromStartFailure(t: Throwable) {
        runCatching { audioEngine.stopTransmit() }
        runCatching { internetNode.stop() }
        runCatching { meshNode.stop() }
        runCatching { stopService(Intent(this, RideService::class.java)) }
        rideStarted = false
        pttPressed = false
        directPeerCount = 0
        binding.startRide.text = "START / JOIN RIDE"
        binding.meshStatus.text = "Hybrid: start failed"
        binding.ptt.text = "BENCH TALK"
        binding.findNearby.isEnabled = true
        binding.showQr.isEnabled = true
        binding.scanQr.isEnabled = true
        log("START ERROR — ${t.javaClass.simpleName}: ${t.message ?: "unknown"}")
        log("The app stayed open so we can diagnose this instead of crashing.")
    }

    private fun radiosReady(): Boolean {
        val bluetoothOn = try {
            val bluetoothManager = getSystemService(BluetoothManager::class.java)
            bluetoothManager.adapter?.isEnabled == true
        } catch (_: Throwable) {
            false
        }

        val wifiOn = try {
            val wifiManager = applicationContext.getSystemService(WifiManager::class.java)
            wifiManager.isWifiEnabled
        } catch (_: Throwable) {
            false
        }

        return bluetoothOn && wifiOn
    }

    private fun stopRide() {
        if (!rideStarted) return
        if (isBenchPttMode()) setPtt(false)
        audioEngine.stopTransmit()
        internetNode.stop()
        meshNode.stop()
        stopService(Intent(this, RideService::class.java))
        rideStarted = false
        pttPressed = false
        directPeerCount = 0
        binding.startRide.text = "START / JOIN RIDE"
        binding.meshStatus.text = "Hybrid: stopped"
        binding.riderCount.text = "Direct peers: 0"
        binding.ptt.text = "BENCH TALK"
        binding.findNearby.isEnabled = true
        binding.showQr.isEnabled = true
        binding.scanQr.isEnabled = true
        binding.findNearby.text = "FIND NEARBY RIDEMESH RIDERS"
        clearNearbyRiders("Tap FIND NEARBY RIDEMESH RIDERS to invite riders.")
        log("Ride stopped")
    }

    private fun updateModeUi() {
        val bench = isBenchPttMode()
        binding.pttLabel.visibility = if (bench) View.VISIBLE else View.GONE
        binding.ptt.visibility = if (bench) View.VISIBLE else View.GONE
        binding.hardwarePtt.visibility = if (bench) View.VISIBLE else View.GONE
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
        if (rideStarted) audioEngine.selectCommunicationDevice()
    }

    private fun restoreSettings() {
        binding.riderName.setText(prefs.getString("rider", Build.MODEL.take(18)))
        binding.rideCode.setText(prefs.getString("code", "RIDE01"))
        binding.hardwarePtt.isChecked = prefs.getBoolean("hardware_ptt", false)
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
            .apply()
    }

    private fun normalizedRideCode(): String = binding.rideCode.text?.toString()
        .orEmpty().trim().uppercase().ifBlank { "RIDE01" }.take(12)

    private fun selectedLabRole(): MeshNode.LabRole {
        return when (binding.labRole.checkedRadioButtonId) {
            R.id.labA -> MeshNode.LabRole.A
            R.id.labB -> MeshNode.LabRole.B
            R.id.labC -> MeshNode.LabRole.C
            else -> MeshNode.LabRole.NORMAL
        }
    }

    private fun hasRequiredPermissions(): Boolean {
        return requiredPermissions().all {
            ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
        }
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

    override fun onLog(message: String) {
        runOnUiThread { log(message) }
    }

    override fun onDirectPeerCount(count: Int) {
        directPeerCount = count
        runOnUiThread {
            binding.riderCount.text = "Direct peers: $count"
            updateTransportStatus()
        }
    }

    override fun onAudioPacket(audio: ByteArray) {
        audioEngine.playIncoming(audio)
    }

    override fun onInternetState(connected: Boolean, message: String) {
        runOnUiThread {
            log(message)
            updateTransportStatus()
        }
    }

    override fun onInternetAudio(audio: ByteArray) {
        if (rideStarted) audioEngine.playIncoming(audio)
    }

    private fun updateTransportStatus() {
        if (!rideStarted) return
        binding.meshStatus.text = if (internetNode.isConnected()) {
            "Hybrid: INTERNET active • mesh peers $directPeerCount"
        } else if (directPeerCount > 0) {
            "Hybrid: LOCAL MESH active • $directPeerCount peers"
        } else {
            "Hybrid: reconnecting • no active path yet"
        }
    }

    override fun onLobbyLog(message: String) {
        runOnUiThread { log(message) }
    }

    override fun onNearbyRiderFound(endpointId: String, riderName: String, rideCode: String) {
        runOnUiThread {
            if (nearbyButtons.containsKey(endpointId)) return@runOnUiThread
            if (nearbyButtons.isEmpty()) binding.nearbyUsers.removeAllViews()

            val button = MaterialButton(this).apply {
                isAllCaps = false
                text = "$riderName • $rideCode   →   INVITE"
                setOnClickListener {
                    lobbyNode.invite(
                        endpointId = endpointId,
                        rideCode = normalizedRideCode(),
                        inviterName = binding.riderName.text?.toString().orEmpty(),
                    )
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
            if (nearbyButtons.isEmpty()) clearNearbyRiders("No RideMesh riders visible yet. Keep FIND active on the other phones.")
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
                    lobbyNode.stop()
                    ensurePermissionsAndRun(PendingAction.START_RIDE)
                }
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
        }
        binding.nearbyUsers.addView(text)
    }

    private fun log(message: String) {
        val stamp = SimpleDateFormat("HH:mm:ss", Locale.US).format(Date())
        val old = binding.logView.text?.toString().orEmpty()
        val next = "$stamp  $message\n$old".take(7000)
        binding.logView.text = next
    }

    private fun isVolumeKey(keyCode: Int): Boolean {
        return keyCode == KeyEvent.KEYCODE_VOLUME_UP || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN
    }

    override fun onDestroy() {
        saveSettings()
        if (::lobbyNode.isInitialized) lobbyNode.stop()
        if (::internetNode.isInitialized && !rideStarted) internetNode.stop()
        if (!rideStarted && ::audioEngine.isInitialized) audioEngine.release()
        super.onDestroy()
    }
}
