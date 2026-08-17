package com.bikemesh.ridemesh

import android.Manifest
import android.bluetooth.BluetoothManager
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.net.wifi.WifiManager
import android.view.KeyEvent
import android.view.MotionEvent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.bikemesh.ridemesh.audio.AudioEngine
import com.bikemesh.ridemesh.audio.AudioRoute
import com.bikemesh.ridemesh.databinding.ActivityMainBinding
import com.bikemesh.ridemesh.mesh.MeshNode
import com.bikemesh.ridemesh.service.RideService
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity(), MeshNode.Listener {
    private lateinit var binding: ActivityMainBinding
    private lateinit var meshNode: MeshNode
    private lateinit var audioEngine: AudioEngine
    private val prefs by lazy { getSharedPreferences("ridemesh", MODE_PRIVATE) }

    private var rideStarted = false
    private var pttPressed = false

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        if (hasRequiredPermissions()) startRideNow()
        else log("Required Nearby/Bluetooth/microphone permission was denied")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        restoreSettings()

        meshNode = MeshNode(applicationContext, this)
        audioEngine = AudioEngine(
            context = applicationContext,
            onCapturedFrame = meshNode::sendLocalAudio,
            onStatus = { text -> runOnUiThread { binding.audioStatus.text = text } },
        )
        applySelectedAudioRoute()

        binding.audioRoute.setOnCheckedChangeListener { _, _ ->
            applySelectedAudioRoute()
            saveSettings()
        }

        binding.hardwarePtt.setOnCheckedChangeListener { _, _ -> saveSettings() }
        binding.labRole.setOnCheckedChangeListener { _, _ -> saveSettings() }

        binding.startRide.setOnClickListener {
            if (rideStarted) stopRide() else ensurePermissionsAndStart()
        }

        binding.ptt.setOnTouchListener { _, event ->
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
        if (rideStarted && binding.hardwarePtt.isChecked && isVolumeKey(keyCode)) {
            if (event?.repeatCount == 0) setPtt(true)
            return true
        }
        return super.onKeyDown(keyCode, event)
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        if (rideStarted && binding.hardwarePtt.isChecked && isVolumeKey(keyCode)) {
            setPtt(false)
            return true
        }
        return super.onKeyUp(keyCode, event)
    }

    private fun setPtt(active: Boolean): Boolean {
        if (!rideStarted || pttPressed == active) return true
        pttPressed = active
        if (active) {
            binding.ptt.text = "TRANSMITTING"
            audioEngine.startTransmit()
        } else {
            binding.ptt.text = "TALK"
            audioEngine.stopTransmit()
        }
        return true
    }

    private fun ensurePermissionsAndStart() {
        val missing = requiredPermissions().filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) startRideNow() else permissionLauncher.launch(missing.toTypedArray())
    }

    private fun startRideNow() {
        if (rideStarted) return
        if (!radiosReady()) {
            log("Turn on Bluetooth and Wi-Fi, then tap START / JOIN RIDE again")
            startActivity(Intent(Settings.ACTION_WIRELESS_SETTINGS))
            return
        }

        val rider = binding.riderName.text?.toString().orEmpty()
        val code = binding.rideCode.text?.toString().orEmpty()
        saveSettings()

        ContextCompat.startForegroundService(this, Intent(this, RideService::class.java))

        rideStarted = true
        applySelectedAudioRoute()
        audioEngine.selectCommunicationDevice()
        meshNode.start(rider, code, selectedLabRole())
        binding.startRide.text = "STOP RIDE"
        binding.meshStatus.text = "Mesh: active • ${code.trim().uppercase()}"
        log("Ride started. Helmet NOT required: Phone A ↔ B first, then A → B → C relay test.")
    }

    private fun radiosReady(): Boolean {
        val bluetoothManager = getSystemService(BluetoothManager::class.java)
        val wifiManager = applicationContext.getSystemService(WifiManager::class.java)
        val bluetoothOn = bluetoothManager.adapter?.isEnabled == true
        val wifiOn = wifiManager.isWifiEnabled
        if (!bluetoothOn) log("Bluetooth is OFF")
        if (!wifiOn) log("Wi-Fi is OFF")
        return bluetoothOn && wifiOn
    }

    private fun stopRide() {
        if (!rideStarted) return
        setPtt(false)
        meshNode.stop()
        stopService(Intent(this, RideService::class.java))
        rideStarted = false
        binding.startRide.text = "START / JOIN RIDE"
        binding.meshStatus.text = "Mesh: stopped"
        binding.riderCount.text = "Direct peers: 0"
        binding.ptt.text = "TALK"
        log("Ride stopped")
    }

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
            .putString("code", binding.rideCode.text?.toString().orEmpty())
            .putString("audio_route", audioRoute)
            .putString("lab_role", selectedLabRole().name)
            .putBoolean("hardware_ptt", binding.hardwarePtt.isChecked)
            .apply()
    }

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
        runOnUiThread { binding.riderCount.text = "Direct peers: $count" }
    }

    override fun onAudioPacket(audio: ByteArray) {
        audioEngine.playIncoming(audio)
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
        if (!rideStarted) audioEngine.release()
        super.onDestroy()
    }
}
