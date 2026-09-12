package com.bikemesh.ridemesh.offline

import android.Manifest
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.ParcelUuid
import androidx.core.content.ContextCompat
import java.security.MessageDigest
import java.util.UUID

/**
 * Android-side companion to [NearbyHotspotAdvertiser].
 *
 * Every rider scans while starting a ride. The advertisement carries the
 * 8-byte ride fingerprint plus an 8-byte deterministic device rank. Only the
 * lower-ranked device yields and becomes client, preventing both Android
 * devices from tearing down their LocalOnlyHotspot at the same time.
 */
class NearbyHotspotClient(
    context: Context,
    private val rideToken: String,
    private val onStatus: (String) -> Unit,
    private val onInvite: (String) -> Unit,
) {
    private val appContext = context.applicationContext
    private val bluetoothManager = appContext.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val handler = Handler(Looper.getMainLooper())
    private val localRank = deviceRank(appContext)
    private val expectedToken = rideTokenBytes(rideToken)

    @Volatile private var started = false
    @Volatile private var connecting = false
    private var scanCallback: ScanCallback? = null
    private var gatt: BluetoothGatt? = null
    private var retryCount = 0

    fun start() {
        if (started) return
        started = true
        if (!hasPermissions()) {
            onStatus("Offline Android discovery needs Bluetooth scan/connect permission")
            return
        }
        val scanner = bluetoothManager.adapter?.bluetoothLeScanner
        if (scanner == null) {
            onStatus("Offline Android discovery unavailable • QR fallback remains available")
            return
        }

        val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(NearbyHotspotAdvertiser.SERVICE_UUID)).build()
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        val callback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) = consider(result)
            override fun onBatchScanResults(results: MutableList<ScanResult>) = results.forEach(::consider)
            override fun onScanFailed(errorCode: Int) {
                if (started) onStatus("Offline Android discovery scan failed • code $errorCode")
            }
        }
        scanCallback = callback
        try {
            scanner.startScan(listOf(filter), settings, callback)
            onStatus("OFFLINE ANDROID DISCOVERY • looking for same-code rider")
        } catch (_: SecurityException) {
            onStatus("Offline Android discovery permission error")
        }
    }

    fun stop() {
        started = false
        connecting = false
        retryCount = 0
        if (hasPermissions()) {
            runCatching { scanCallback?.let { bluetoothManager.adapter?.bluetoothLeScanner?.stopScan(it) } }
            runCatching { gatt?.disconnect() }
            runCatching { gatt?.close() }
        }
        scanCallback = null
        gatt = null
    }

    private fun consider(result: ScanResult) {
        if (!started || connecting) return
        val data = result.scanRecord?.getServiceData(ParcelUuid(NearbyHotspotAdvertiser.SERVICE_UUID)) ?: return
        if (data.size < 16) return
        if (!data.copyOfRange(0, 8).contentEquals(expectedToken)) return
        val remoteRank = data.copyOfRange(8, 16)

        // Higher rank remains host; lower rank becomes client.
        if (compareUnsigned(localRank, remoteRank) >= 0) return

        connecting = true
        onStatus("OFFLINE SAME-CODE RIDER FOUND • preparing direct Wi-Fi link")
        stopScanOnly()
        connectGatt(result.device)
    }

    private fun stopScanOnly() {
        if (!hasPermissions()) return
        runCatching { scanCallback?.let { bluetoothManager.adapter?.bluetoothLeScanner?.stopScan(it) } }
    }

    @Suppress("DEPRECATION")
    private fun connectGatt(device: BluetoothDevice) {
        if (!started || !hasPermissions()) return
        val callback = object : BluetoothGattCallback() {
            override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
                if (!started) return
                if (status == BluetoothGatt.GATT_SUCCESS && newState == BluetoothProfile.STATE_CONNECTED) {
                    onStatus("Offline rider authenticated over Bluetooth • reading Wi-Fi invitation")
                    runCatching { g.discoverServices() }
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    if (gatt === g) {
                        runCatching { g.close() }
                        gatt = null
                    }
                    if (started && connecting) {
                        connecting = false
                        handler.postDelayed({ if (started) startAgain() }, 1200L)
                    }
                }
            }

            override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
                if (status != BluetoothGatt.GATT_SUCCESS) return
                val characteristic = g.getService(NearbyHotspotAdvertiser.SERVICE_UUID)
                    ?.getCharacteristic(NearbyHotspotAdvertiser.CHARACTERISTIC_UUID)
                    ?: run {
                        onStatus("Same-code rider found but invitation service is missing")
                        return
                    }
                readSecureInvite(g, characteristic)
            }

            override fun onCharacteristicRead(
                g: BluetoothGatt,
                characteristic: BluetoothGattCharacteristic,
                status: Int,
            ) {
                if (characteristic.uuid != NearbyHotspotAdvertiser.CHARACTERISTIC_UUID) return
                if (status == BluetoothGatt.GATT_SUCCESS) {
                    val text = characteristic.value?.toString(Charsets.UTF_8).orEmpty()
                    if (text.startsWith("ridemesh://offline?")) {
                        connecting = false
                        onStatus("OFFLINE INVITATION RECEIVED • switching to direct Wi-Fi")
                        onInvite(text)
                        stop()
                    }
                    return
                }
                if (status == BluetoothGatt.GATT_INSUFFICIENT_AUTHENTICATION ||
                    status == BluetoothGatt.GATT_INSUFFICIENT_ENCRYPTION
                ) {
                    beginBondAndRetry(g.device, g, characteristic)
                } else {
                    onStatus("Offline invitation read failed • GATT $status")
                }
            }
        }
        try {
            gatt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                device.connectGatt(appContext, false, callback, BluetoothDevice.TRANSPORT_LE)
            } else {
                device.connectGatt(appContext, false, callback)
            }
        } catch (_: SecurityException) {
            connecting = false
            onStatus("Offline Android discovery Bluetooth permission error")
        }
    }

    @Suppress("DEPRECATION")
    private fun readSecureInvite(g: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
        if (!started || !hasPermissions()) return
        if (g.device.bondState == BluetoothDevice.BOND_BONDED) {
            runCatching { g.readCharacteristic(characteristic) }
        } else {
            beginBondAndRetry(g.device, g, characteristic)
        }
    }

    @Suppress("DEPRECATION")
    private fun beginBondAndRetry(
        device: BluetoothDevice,
        g: BluetoothGatt,
        characteristic: BluetoothGattCharacteristic,
    ) {
        if (!started || !hasPermissions()) return
        if (device.bondState == BluetoothDevice.BOND_NONE) {
            onStatus("Confirm the Android Bluetooth pairing request once")
            runCatching { device.createBond() }
        }
        retryCount = 0
        fun retry() {
            if (!started || gatt !== g) return
            if (device.bondState == BluetoothDevice.BOND_BONDED) {
                runCatching { g.readCharacteristic(characteristic) }
                return
            }
            retryCount += 1
            if (retryCount >= 25) {
                onStatus("Offline rider pairing timed out • retry the ride")
                connecting = false
                return
            }
            handler.postDelayed(::retry, 800L)
        }
        handler.postDelayed(::retry, 500L)
    }

    private fun startAgain() {
        if (!started) return
        stopScanOnly()
        scanCallback = null
        started = false
        start()
    }

    private fun hasPermissions(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_SCAN) == PackageManager.PERMISSION_GRANTED &&
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
    }

    private fun rideTokenBytes(token: String): ByteArray = token.chunked(2).take(8)
        .map { it.toInt(16).toByte() }.toByteArray()

    companion object {
        private const val PREFS = "ridemesh_offline_bootstrap"
        private const val KEY_RANK_SEED = "device_rank_seed"

        fun deviceRank(context: Context): ByteArray {
            val prefs = context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val seed = prefs.getString(KEY_RANK_SEED, null)?.takeIf { it.isNotBlank() }
                ?: UUID.randomUUID().toString().also { prefs.edit().putString(KEY_RANK_SEED, it).apply() }
            return MessageDigest.getInstance("SHA-256")
                .digest(seed.toByteArray(Charsets.UTF_8))
                .copyOfRange(0, 8)
        }

        private fun compareUnsigned(a: ByteArray, b: ByteArray): Int {
            for (i in 0 until minOf(a.size, b.size)) {
                val av = a[i].toInt() and 0xff
                val bv = b[i].toInt() and 0xff
                if (av != bv) return av.compareTo(bv)
            }
            return a.size.compareTo(b.size)
        }
    }
}
