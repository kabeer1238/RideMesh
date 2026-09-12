package com.bikemesh.ridemesh.service

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.bikemesh.ridemesh.R

class RideService : Service() {
    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_headset)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("RideMesh WebRTC intercom is active")
            .setOngoing(true)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .build()

        val locationGranted =
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
        val fullTypes = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or
            ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE or
            (if (locationGranted) ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION else 0)

        try {
            ServiceCompat.startForeground(this, NOTIFICATION_ID, notification, fullTypes)
        } catch (_: SecurityException) {
            // Some Android/OEM builds enforce microphone FGS prerequisites more strictly.
            // Keep the ride process alive with the connected-device type instead of
            // allowing an uncaught SecurityException to terminate the whole app.
            try {
                ServiceCompat.startForeground(
                    this,
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE,
                )
            } catch (_: Throwable) {
                stopSelf()
                return START_NOT_STICKY
            }
        } catch (_: Throwable) {
            stopSelf()
            return START_NOT_STICKY
        }

        return START_NOT_STICKY
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // A Recents swipe is treated as an explicit app close. Release the
        // Activity-owned voice/location runtime before this foreground service exits.
        RideShutdownCoordinator.requestShutdown()
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL, "Active ride", NotificationManager.IMPORTANCE_LOW)
        )
    }

    companion object {
        private const val CHANNEL = "ride_mesh_active"
        private const val NOTIFICATION_ID = 7101
    }
}
