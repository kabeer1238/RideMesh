package com.bikemesh.ridemesh.offline

import android.Manifest
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.ParcelUuid
import androidx.core.content.ContextCompat
import java.util.UUID

/**
 * BLE bootstrap for the temporary Android LocalOnlyHotspot.
 *
 * Advertising exposes only the ride-token fingerprint. The SSID/password QR
 * payload is readable solely from a characteristic protected by an encrypted,
 * authenticated OS Bluetooth bond.
 */
class NearbyHotspotAdvertiser(
    context: Context,
    private val rideToken: String,
    invitePayload: String,
    private val onStatus: (String) -> Unit,
) {
    private val appContext = context.applicationContext
    private val bluetoothManager = appContext.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val inviteBytes = invitePayload.toByteArray(Charsets.UTF_8)
    private var gattServer: BluetoothGattServer? = null
    private var advertiseCallback: AdvertiseCallback? = null

    fun start() {
        if (!hasPermissions()) {
            onStatus("Offline nearby discovery needs Bluetooth permission")
            return
        }
        val adapter = bluetoothManager.adapter
        val advertiser = adapter?.bluetoothLeAdvertiser
        if (advertiser == null || adapter.isMultipleAdvertisementSupported != true) {
            onStatus("Offline nearby discovery unavailable • QR still available")
            return
        }

        val characteristic = BluetoothGattCharacteristic(
            CHARACTERISTIC_UUID,
            BluetoothGattCharacteristic.PROPERTY_READ,
            BluetoothGattCharacteristic.PERMISSION_READ_ENCRYPTED_MITM,
        ).apply { value = inviteBytes }
        val service = BluetoothGattService(SERVICE_UUID, BluetoothGattService.SERVICE_TYPE_PRIMARY).apply {
            addCharacteristic(characteristic)
        }
        val callback = object : BluetoothGattServerCallback() {
            @Suppress("DEPRECATION")
            override fun onCharacteristicReadRequest(
                device: android.bluetooth.BluetoothDevice,
                requestId: Int,
                offset: Int,
                requested: BluetoothGattCharacteristic,
            ) {
                if (requested.uuid != CHARACTERISTIC_UUID) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_REQUEST_NOT_SUPPORTED, offset, null)
                    return
                }
                if (offset > inviteBytes.size) {
                    gattServer?.sendResponse(device, requestId, BluetoothGatt.GATT_INVALID_OFFSET, offset, null)
                    return
                }
                gattServer?.sendResponse(
                    device,
                    requestId,
                    BluetoothGatt.GATT_SUCCESS,
                    offset,
                    inviteBytes.copyOfRange(offset, inviteBytes.size),
                )
            }
        }
        gattServer = bluetoothManager.openGattServer(appContext, callback)?.also { it.addService(service) }
        if (gattServer == null) {
            onStatus("Offline nearby secure service failed • QR still available")
            return
        }

        val uuid = ParcelUuid(SERVICE_UUID)
        val primary = AdvertiseData.Builder().setIncludeDeviceName(false).addServiceUuid(uuid).build()
        val scanResponse = AdvertiseData.Builder()
            .setIncludeDeviceName(false)
            .addServiceData(uuid, rideTokenBytes())
            .build()
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(true)
            .setTimeout(0)
            .build()
        val advertise = object : AdvertiseCallback() {
            override fun onStartSuccess(settingsInEffect: AdvertiseSettings) {
                onStatus("OFFLINE NEARBY READY • same code auto-discovers")
            }

            override fun onStartFailure(errorCode: Int) {
                onStatus("Offline nearby discovery failed • code $errorCode • QR still available")
            }
        }
        advertiseCallback = advertise
        try {
            advertiser.startAdvertising(settings, primary, scanResponse, advertise)
        } catch (_: SecurityException) {
            onStatus("Offline nearby discovery permission error")
        }
    }

    fun stop() {
        val adapter = bluetoothManager.adapter
        if (hasPermissions()) {
            runCatching { advertiseCallback?.let { adapter?.bluetoothLeAdvertiser?.stopAdvertising(it) } }
            runCatching { gattServer?.clearServices() }
            runCatching { gattServer?.close() }
        }
        advertiseCallback = null
        gattServer = null
    }

    private fun hasPermissions(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        return ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_ADVERTISE) == PackageManager.PERMISSION_GRANTED &&
            ContextCompat.checkSelfPermission(appContext, Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED
    }

    private fun rideTokenBytes(): ByteArray = rideToken.chunked(2).take(8)
        .map { it.toInt(16).toByte() }.toByteArray()

    companion object {
        val SERVICE_UUID: UUID = UUID.fromString("c0de4935-7a11-4e7f-9a6d-524944454d53")
        val CHARACTERISTIC_UUID: UUID = UUID.fromString("c0de4936-7a11-4e7f-9a6d-524944454d53")
    }
}
