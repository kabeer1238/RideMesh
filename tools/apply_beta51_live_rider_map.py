from pathlib import Path
import re

ROOT = Path('.')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    return text.replace(old, new, 1)


# -----------------------------------------------------------------------------
# Gradle: vc19 + Google Maps / fused location. API key is injected at build time
# from Gradle property MAPS_API_KEY or environment variable MAPS_API_KEY.
# -----------------------------------------------------------------------------
p = ROOT / 'app/build.gradle.kts'
s = p.read_text()
s = s.replace('versionCode = 18', 'versionCode = 19')
s = s.replace('versionName = "1.0.0-beta5.0-adaptive-reliability"', 'versionName = "1.0.0-beta5.1-live-rider-map"')

if 'manifestPlaceholders["MAPS_API_KEY"]' not in s:
    anchor = '        versionName = "1.0.0-beta5.1-live-rider-map"\n'
    addition = '''        versionName = "1.0.0-beta5.1-live-rider-map"\n        manifestPlaceholders["MAPS_API_KEY"] =\n            (project.findProperty("MAPS_API_KEY") as String?)\n                ?: System.getenv("MAPS_API_KEY")\n                ?: ""\n'''
    s = replace_once(s, anchor, addition, 'maps api key placeholder')

if 'play-services-maps' not in s:
    anchor = '    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")\n'
    addition = anchor + '    implementation("com.google.android.gms:play-services-maps:19.2.0")\n    implementation("com.google.android.gms:play-services-location:21.3.0")\n'
    s = replace_once(s, anchor, addition, 'maps dependencies')
p.write_text(s)


# -----------------------------------------------------------------------------
# Manifest: location permissions, Maps key, and location-capable foreground ride.
# Location remains optional to voice: denying location never blocks the ride.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/AndroidManifest.xml'
s = p.read_text()
if 'android.permission.ACCESS_FINE_LOCATION' not in s:
    anchor = '    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />\n'
    addition = anchor + '''    <uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />\n    <uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />\n'''
    s = replace_once(s, anchor, addition, 'location permissions')
if 'android.permission.FOREGROUND_SERVICE_LOCATION' not in s:
    anchor = '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE" />\n'
    s = replace_once(s, anchor, anchor + '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_LOCATION" />\n', 'location fgs permission')
if 'com.google.android.geo.API_KEY' not in s:
    anchor = '''        <meta-data\n            android:name="com.google.mlkit.vision.DEPENDENCIES"\n            android:value="barcode_ui" />\n'''
    addition = anchor + '''\n        <meta-data\n            android:name="com.google.android.geo.API_KEY"\n            android:value="${MAPS_API_KEY}" />\n'''
    s = replace_once(s, anchor, addition, 'maps metadata')
s = s.replace('android:foregroundServiceType="microphone|connectedDevice"', 'android:foregroundServiceType="microphone|connectedDevice|location"')
p.write_text(s)


# -----------------------------------------------------------------------------
# RideService: declare location type only when location permission is granted.
# This keeps voice foreground-service startup safe for riders who decline map GPS.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/service/RideService.kt'
s = p.read_text()
if 'import android.Manifest' not in s:
    s = s.replace('package com.bikemesh.ridemesh.service\n\n', 'package com.bikemesh.ridemesh.service\n\nimport android.Manifest\n')
if 'import android.content.pm.PackageManager' not in s:
    s = s.replace('import android.content.pm.ServiceInfo\n', 'import android.content.pm.PackageManager\nimport android.content.pm.ServiceInfo\n')
if 'import androidx.core.content.ContextCompat' not in s:
    s = s.replace('import androidx.core.app.ServiceCompat\n', 'import androidx.core.app.ServiceCompat\nimport androidx.core.content.ContextCompat\n')
old_types = '''        val fullTypes = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or\n            ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE\n'''
new_types = '''        val locationGranted =\n            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||\n                ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED\n        val fullTypes = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or\n            ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE or\n            (if (locationGranted) ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION else 0)\n'''
if 'val locationGranted =' not in s:
    s = replace_once(s, old_types, new_types, 'ride service location type')
p.write_text(s)


# -----------------------------------------------------------------------------
# InternetNode: room-scoped, lightweight location packets on a dedicated MQTT topic.
# Audio remains WebRTC/SRTP and never shares this payload path.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/transport/InternetNode.kt'
s = p.read_text()

listener_anchor = '        fun onInternetAudioStatus(message: String) = Unit\n'
if 'onInternetRiderLocation' not in s:
    s = replace_once(
        s,
        listener_anchor,
        listener_anchor + '        fun onInternetRiderLocation(location: RiderLocation) = Unit\n',
        'location listener',
    )

rider_model_anchor = '    data class Diagnostics(\n'
if 'data class RiderLocation(' not in s:
    model = '''    data class RiderLocation(\n        val riderId: UUID,\n        val displayName: String,\n        val latitude: Double,\n        val longitude: Double,\n        val speedKmh: Float,\n        val heading: Float,\n        val timestampMs: Long,\n        val connectionQuality: String,\n        val phoneNumber: String = "",\n    )\n\n'''
    s = replace_once(s, rider_model_anchor, model + rider_model_anchor, 'rider location model')

if '@Volatile private var locationTopic:' not in s:
    anchor = '    @Volatile private var signalTopic: String = ""\n'
    s = replace_once(s, anchor, anchor + '    @Volatile private var locationTopic: String = ""\n', 'location topic state')

if 'locationTopic = "$baseTopic/location"' not in s:
    anchor = '        signalTopic = "$baseTopic/signal"\n'
    s = replace_once(s, anchor, anchor + '        locationTopic = "$baseTopic/location"\n', 'location topic setup')

if 'fun publishRiderLocation(' not in s:
    anchor = '    fun currentAudioStatus(): String = audioStatus\n\n'
    helpers = r'''    fun localRiderId(): UUID = nodeId

    fun currentConnectionQualityLabel(): String {
        val active = sessions.values.filter { it.connected }
        if (!signalingConnected.get() && active.isEmpty()) return "Reconnecting"
        if (active.any { it.measuredQualityLabel.equals("Poor", true) }) return "Poor"
        if (active.isNotEmpty() && active.all { it.measuredQualityLabel.equals("Excellent", true) }) return "Excellent"
        return "Good"
    }

    fun publishRiderLocation(
        latitude: Double,
        longitude: Double,
        speedKmh: Float,
        heading: Float,
        phoneNumber: String = "",
    ): Boolean {
        if (!running.get() || !signalingConnected.get()) return false
        if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0) return false
        val packet = RiderLocation(
            riderId = nodeId,
            displayName = riderName,
            latitude = latitude,
            longitude = longitude,
            speedKmh = speedKmh.coerceIn(0f, 450f),
            heading = ((heading % 360f) + 360f) % 360f,
            timestampMs = System.currentTimeMillis(),
            connectionQuality = currentConnectionQualityLabel(),
            phoneNumber = sanitizePhone(phoneNumber),
        )
        return runCatching {
            sendMqttPublish(locationTopic, encodeLocation(packet))
            true
        }.getOrDefault(false)
    }

'''
    s = replace_once(s, anchor, anchor + helpers, 'location public helpers')

handle_anchor = '''        when (receivedTopic) {\n            presenceTopic -> handlePresence(payload)\n            signalTopic -> decodeSignal(payload)?.let(::handleSignal)\n        }\n'''
handle_new = '''        when (receivedTopic) {\n            presenceTopic -> handlePresence(payload)\n            signalTopic -> decodeSignal(payload)?.let(::handleSignal)\n            locationTopic -> decodeLocation(payload)?.let { location ->\n                if (location.riderId != nodeId) listener.onInternetRiderLocation(location)\n            }\n        }\n'''
if 'locationTopic -> decodeLocation' not in s:
    s = replace_once(s, handle_anchor, handle_new, 'location topic receive')

if 'internal fun encodeLocation(' not in s:
    anchor = '''    // -------------------------------------------------------------------------\n    // Legacy-compatible presence/audio helpers retained for existing unit tests.\n    // -------------------------------------------------------------------------\n'''
    codec = r'''    // -------------------------------------------------------------------------
    // Live Rider Map location codec. Fixed binary contract for Android/iOS parity.
    // Room isolation is provided by the existing ride-code MQTT topic namespace.
    // -------------------------------------------------------------------------

    internal fun encodeLocation(packet: RiderLocation): ByteArray {
        val nameBytes = packet.displayName.toByteArray(Charsets.UTF_8).let {
            if (it.size > MAX_RIDER_NAME_BYTES) it.copyOf(MAX_RIDER_NAME_BYTES) else it
        }
        val phoneBytes = sanitizePhone(packet.phoneNumber).toByteArray(Charsets.UTF_8).let {
            if (it.size > MAX_PHONE_BYTES) it.copyOf(MAX_PHONE_BYTES) else it
        }
        val qualityCode = when (packet.connectionQuality.lowercase()) {
            "excellent" -> 1
            "good" -> 2
            "poor" -> 3
            "reconnecting" -> 4
            else -> 0
        }
        return ByteBuffer.allocate(LOCATION_FIXED_BYTES + nameBytes.size + phoneBytes.size)
            .order(ByteOrder.BIG_ENDIAN)
            .putInt(LOCATION_MAGIC)
            .put(LOCATION_VERSION)
            .putLong(packet.riderId.mostSignificantBits)
            .putLong(packet.riderId.leastSignificantBits)
            .putLong(packet.timestampMs)
            .putDouble(packet.latitude)
            .putDouble(packet.longitude)
            .putFloat(packet.speedKmh.coerceIn(0f, 450f))
            .putFloat(((packet.heading % 360f) + 360f) % 360f)
            .put(qualityCode.toByte())
            .put(nameBytes.size.toByte())
            .put(nameBytes)
            .put(phoneBytes.size.toByte())
            .put(phoneBytes)
            .array()
    }

    internal fun decodeLocation(payload: ByteArray): RiderLocation? {
        if (payload.size < LOCATION_FIXED_BYTES) return null
        return try {
            val buffer = ByteBuffer.wrap(payload).order(ByteOrder.BIG_ENDIAN)
            if (buffer.int != LOCATION_MAGIC || buffer.get() != LOCATION_VERSION) return null
            val riderId = UUID(buffer.long, buffer.long)
            val timestampMs = buffer.long
            val latitude = buffer.double
            val longitude = buffer.double
            val speedKmh = buffer.float
            val heading = buffer.float
            val quality = when (buffer.get().toInt() and 0xff) {
                1 -> "Excellent"
                2 -> "Good"
                3 -> "Poor"
                4 -> "Reconnecting"
                else -> "Good"
            }
            if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0) return null
            if (!buffer.hasRemaining()) return null
            val nameLength = buffer.get().toInt() and 0xff
            if (nameLength > MAX_RIDER_NAME_BYTES || nameLength > buffer.remaining()) return null
            val nameBytes = ByteArray(nameLength)
            buffer.get(nameBytes)
            if (!buffer.hasRemaining()) return null
            val phoneLength = buffer.get().toInt() and 0xff
            if (phoneLength > MAX_PHONE_BYTES || phoneLength > buffer.remaining()) return null
            val phoneBytes = ByteArray(phoneLength)
            buffer.get(phoneBytes)
            RiderLocation(
                riderId = riderId,
                displayName = nameBytes.toString(Charsets.UTF_8).trim().ifBlank { "Rider" },
                latitude = latitude,
                longitude = longitude,
                speedKmh = speedKmh.coerceIn(0f, 450f),
                heading = ((heading % 360f) + 360f) % 360f,
                timestampMs = timestampMs,
                connectionQuality = quality,
                phoneNumber = sanitizePhone(phoneBytes.toString(Charsets.UTF_8)),
            )
        } catch (_: Throwable) {
            null
        }
    }

    private fun sanitizePhone(value: String): String = value
        .trim()
        .filter { it.isDigit() || it == '+' || it == ' ' || it == '-' || it == '(' || it == ')' }
        .take(MAX_PHONE_BYTES)

'''
    s = replace_once(s, anchor, codec + anchor, 'location codec')

if 'private const val LOCATION_MAGIC' not in s:
    anchor = '        private const val PRESENCE_BASE_BYTES = 24\n'
    constants = '''        private const val LOCATION_MAGIC = 0x524D4C31 // RML1\n        private const val LOCATION_VERSION: Byte = 1\n        private const val LOCATION_FIXED_BYTES = 56\n        private const val MAX_PHONE_BYTES = 32\n\n'''
    s = replace_once(s, anchor, constants + anchor, 'location constants')

p.write_text(s)


# -----------------------------------------------------------------------------
# MainActivity: map UI, location lifecycle, marker rendering, rider card/actions,
# optional phone profile. Location denial never stops voice.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

import_replacements = {
    'import android.graphics.Bitmap\n': 'import android.graphics.Bitmap\nimport android.graphics.Canvas\nimport android.graphics.Paint\nimport android.graphics.Path\nimport android.graphics.RectF\n',
    'import android.net.Uri\n': 'import android.net.Uri\nimport android.location.Location\n',
    'import android.widget.GridLayout\n': 'import android.widget.FrameLayout\nimport android.widget.GridLayout\n',
    'import android.widget.TextView\n': 'import android.widget.TextView\nimport android.widget.Toast\n',
    'import androidx.core.content.FileProvider\n': 'import androidx.core.content.FileProvider\nimport androidx.core.graphics.ColorUtils\n',
    'import com.google.android.gms.mlkit.barcode.GmsBarcodeScannerOptions\n': 'import com.google.android.gms.location.FusedLocationProviderClient\nimport com.google.android.gms.location.LocationCallback\nimport com.google.android.gms.location.LocationRequest\nimport com.google.android.gms.location.LocationResult\nimport com.google.android.gms.location.LocationServices\nimport com.google.android.gms.location.Priority\nimport com.google.android.gms.maps.CameraUpdateFactory\nimport com.google.android.gms.maps.GoogleMap\nimport com.google.android.gms.maps.MapStyleOptions\nimport com.google.android.gms.maps.SupportMapFragment\nimport com.google.android.gms.maps.model.BitmapDescriptorFactory\nimport com.google.android.gms.maps.model.LatLng\nimport com.google.android.gms.maps.model.LatLngBounds\nimport com.google.android.gms.maps.model.Marker\nimport com.google.android.gms.maps.model.MarkerOptions\nimport com.google.android.gms.mlkit.barcode.GmsBarcodeScannerOptions\n',
    'import kotlin.random.Random\n': 'import kotlin.math.roundToInt\nimport kotlin.random.Random\n',
}
for old, new in import_replacements.items():
    if new not in s:
        s = replace_once(s, old, new, f'import {old.strip()}')

if 'import android.text.InputType' not in s:
    s = s.replace('import android.os.Looper\n', 'import android.os.Looper\nimport android.text.InputType\n')
if 'import android.widget.EditText' not in s:
    s = s.replace('import android.widget.FrameLayout\n', 'import android.widget.EditText\nimport android.widget.FrameLayout\n')

s = s.replace('    private enum class Screen { HOME, SETUP, ACTIVE }', '    private enum class Screen { HOME, SETUP, ACTIVE, MAP }')

state_anchor = '    private val speakingUntilMs = ConcurrentHashMap<String, Long>()\n'
if 'private val riderLocations' not in s:
    state = r'''    private val riderLocations = ConcurrentHashMap<String, InternetNode.RiderLocation>()
    private val riderMapMarkers = mutableMapOf<String, Marker>()
    private var myLiveLocation: InternetNode.RiderLocation? = null
    private var fusedLocationClient: FusedLocationProviderClient? = null
    private var liveLocationCallback: LocationCallback? = null
    private var liveMap: GoogleMap? = null
    private var liveMapScreen: LinearLayout? = null
    private var liveMapHost: FrameLayout? = null
    private var liveMapStatus: TextView? = null
    private var liveMapShareStatus: TextView? = null
    private var liveMapVisible = false
    private var appInForeground = true
    private var lastLocationPublishMs = 0L
    private var lastPublishedLocation: Location? = null
    private var lastMapFitMs = 0L
    private var selectedMapRiderId: String? = null

'''
    s = replace_once(s, state_anchor, state_anchor + state, 'map state')

if 'locationPermissionLauncher' not in s:
    oncreate_anchor = '    override fun onCreate(savedInstanceState: Bundle?) {\n'
    launcher = r'''    private val locationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) {
        if (hasLocationPermission()) {
            if (rideStarted) startRideServiceSafely()
            startLiveLocationSharing()
            if (liveMapVisible) renderLiveRiderMap(fitGroup = true)
        } else {
            liveMapStatus?.text = "LOCATION OFF • VOICE UNAFFECTED"
            Toast.makeText(this, "Location permission is optional. RideMesh voice continues normally.", Toast.LENGTH_LONG).show()
        }
    }

'''
    s = replace_once(s, oncreate_anchor, launcher + oncreate_anchor, 'location permission launcher')

if 'fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)' not in s:
    anchor = '        audioEngine = AudioEngine(\n'
    s = replace_once(s, anchor, '        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)\n\n' + anchor, 'fused location init')

if 'installRideMainNavigation()' not in s:
    anchor = '        applyPowerUi()\n\n'
    s = replace_once(s, anchor, anchor + '        installRideMainNavigation()\n\n', 'main navigation install')

show_pattern = re.compile(r'''    private fun showScreen\(screen: Screen\) \{.*?\n    \}\n\n    private fun ensurePermissionsAndRun''', re.S)
if 'liveMapVisible = screen == Screen.MAP' not in s:
    replacement = r'''    private fun showScreen(screen: Screen) {
        binding.screenHome.visibility = if (screen == Screen.HOME) View.VISIBLE else View.GONE
        binding.screenSetup.visibility = if (screen == Screen.SETUP) View.VISIBLE else View.GONE
        binding.screenActive.visibility = if (screen == Screen.ACTIVE) View.VISIBLE else View.GONE
        liveMapVisible = screen == Screen.MAP
        liveMapScreen?.visibility = if (liveMapVisible) View.VISIBLE else View.GONE
        if (liveMapVisible) {
            ensureLocationSharingPermission()
            ensureGoogleMapReady()
            updateLiveMapHeader()
            renderLiveRiderMap(fitGroup = true)
        }
    }

    private fun ensurePermissionsAndRun'''
    s, count = show_pattern.subn(replacement, s, count=1)
    if count != 1:
        raise SystemExit('showScreen replacement failed')

if 'beginLiveMapSession()' not in s:
    anchor = '''            internetNode.start(code, rider, deviceLabel())\n            internetNode.setMuted(micMuted)\n            applySelectedAudioRoute()\n'''
    s = replace_once(s, anchor, anchor + '            beginLiveMapSession()\n', 'start live map session')

if 'endLiveMapSession()' not in s:
    stop_anchor = '''        audioEngine.stopTransmit()\n        internetNode.stop()\n        meshRunning = false\n'''
    stop_new = '''        audioEngine.stopTransmit()\n        endLiveMapSession()\n        internetNode.stop()\n        meshRunning = false\n'''
    s = replace_once(s, stop_anchor, stop_new, 'stop live map session')
    recover_anchor = '''        runCatching { audioEngine.stopTransmit() }\n        runCatching { internetNode.stop() }\n'''
    recover_new = '''        runCatching { audioEngine.stopTransmit() }\n        runCatching { endLiveMapSession() }\n        runCatching { internetNode.stop() }\n'''
    s = replace_once(s, recover_anchor, recover_new, 'recover live map session')

if 'override fun onInternetRiderLocation' not in s:
    anchor = '''    override fun onInternetAudioStatus(message: String) {\n        runOnUiThread {\n            if (rideStarted) updateAudioUi(message)\n        }\n    }\n\n'''
    callback = r'''    override fun onInternetRiderLocation(location: InternetNode.RiderLocation) {
        if (!rideStarted) return
        riderLocations[location.riderId.toString()] = location
        runOnUiThread {
            updateLiveMapHeader()
            if (liveMapVisible) renderLiveRiderMap(fitGroup = false)
        }
    }

'''
    s = replace_once(s, anchor, anchor + callback, 'location callback')

if 'if (liveMapVisible) renderLiveRiderMap(fitGroup = false)' not in s[s.find('private fun updateTransportStatus'):s.find('private fun markRiderSpeaking')]:
    anchor = '        renderRiderGrid()\n        applyPowerUi()\n'
    s = replace_once(s, anchor, '        renderRiderGrid()\n        updateLiveMapHeader()\n        if (liveMapVisible) renderLiveRiderMap(fitGroup = false)\n        applyPowerUi()\n', 'map refresh transport status')

if 'private fun showRiderPhoneEditor()' not in s:
    anchor = '    private fun showRidersDialog() {\n'
    helper = r'''    private fun showRiderPhoneEditor() {
        showRideMeshPanel(
            "RIDER PHONE",
            "Optional. Shared only with riders in your active RideMesh group so they can open the dialer or messaging app."
        ) { body, dialog ->
            val input = EditText(this).apply {
                setText(prefs.getString(RIDER_PHONE_KEY, "").orEmpty())
                hint = "+91 98765 43210"
                inputType = InputType.TYPE_CLASS_PHONE
                setSingleLine(true)
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
                setHintTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
                backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.accent))
            }
            body.addView(input, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56)))
            addPanelButton(body, "SAVE PHONE") {
                val phone = normalizeRiderPhone(input.text?.toString().orEmpty())
                prefs.edit().putString(RIDER_PHONE_KEY, phone).apply()
                dialog.dismiss()
            }
            addPanelButton(body, "REMOVE PHONE", primary = false) {
                prefs.edit().remove(RIDER_PHONE_KEY).apply()
                dialog.dismiss()
            }
        }
    }

    private fun normalizeRiderPhone(value: String): String = value
        .trim()
        .filter { it.isDigit() || it == '+' || it == ' ' || it == '-' || it == '(' || it == ')' }
        .take(32)

'''
    s = replace_once(s, anchor, helper + anchor, 'phone editor helper')

if 'EDIT PHONE NUMBER' not in s:
    anchor = '            addPanelInfo(body, "Email", email)\n'
    if anchor in s:
        s = s.replace(anchor, anchor + '            val phone = prefs.getString(RIDER_PHONE_KEY, "").orEmpty().ifBlank { "Not set" }\n            addPanelInfo(body, "Phone", phone)\n', 1)
        button_anchor = '''            addPanelButton(body, "EDIT RIDER NAME") {\n                dialog.dismiss()\n                showRiderNameEditor()\n            }\n'''
        if button_anchor in s:
            s = s.replace(button_anchor, button_anchor + '''            addPanelButton(body, "EDIT PHONE NUMBER", primary = false) {\n                dialog.dismiss()\n                showRiderPhoneEditor()\n            }\n''', 1)

if 'override fun onResume()' not in s:
    anchor = '    override fun onDestroy() {\n'
    lifecycle = r'''    override fun onResume() {
        super.onResume()
        appInForeground = true
    }

    override fun onPause() {
        appInForeground = false
        super.onPause()
    }

'''
    if anchor in s:
        s = s.replace(anchor, lifecycle + anchor, 1)

if 'private fun installRideMainNavigation()' not in s:
    anchor = '    private fun dp(value: Int): Int = '
    idx = s.find(anchor)
    if idx < 0:
        anchor = '    override fun onDestroy() {'
        idx = s.find(anchor)
    if idx < 0:
        raise SystemExit('map helper insertion anchor not found')

    helpers = r'''    private fun installRideMainNavigation() {
        if (liveMapScreen != null) return

        binding.screenActive.addView(
            buildRideMainNav(Screen.ACTIVE),
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(58)).apply {
                topMargin = dp(4)
            }
        )

        val screen = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            setPadding(dp(14), dp(12), dp(14), dp(10))
            visibility = View.GONE
        }

        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_logo_exact)
            scaleType = ImageView.ScaleType.FIT_START
            contentDescription = "RideMesh by Autopilot India"
        }
        screen.addView(logo, LinearLayout.LayoutParams(dp(220), dp(58)))

        liveMapStatus = TextView(this).apply {
            text = "● LIVE • 1 RIDER"
            textSize = 16f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.accent))
        }
        screen.addView(liveMapStatus, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(28)).apply {
            topMargin = dp(2)
        })

        liveMapShareStatus = TextView(this).apply {
            text = "Location shared only with this active RideMesh group"
            textSize = 10.5f
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
        }
        screen.addView(liveMapShareStatus, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(24)))

        val host = FrameLayout(this).apply {
            id = View.generateViewId()
            background = GradientDrawable().apply {
                cornerRadius = dp(18).toFloat()
                setColor(Color.parseColor("#07100F"))
                setStroke(dp(1), ContextCompat.getColor(this@MainActivity, R.color.border))
            }
        }
        liveMapHost = host
        screen.addView(host, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f).apply {
            topMargin = dp(6)
            bottomMargin = dp(8)
        })

        screen.addView(buildRideMainNav(Screen.MAP), LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(58)))
        (binding.root as ViewGroup).addView(
            screen,
            FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT)
        )
        liveMapScreen = screen
    }

    private fun buildRideMainNav(selected: Screen): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        fun add(label: String, selectedHere: Boolean, action: () -> Unit) {
            val button = MaterialButton(this).apply {
                text = label
                textSize = 9.5f
                setTypeface(Typeface.DEFAULT, Typeface.BOLD)
                cornerRadius = dp(12)
                strokeWidth = dp(1)
                strokeColor = ColorStateList.valueOf(
                    ContextCompat.getColor(this@MainActivity, if (selectedHere) R.color.accent else R.color.border)
                )
                backgroundTintList = ColorStateList.valueOf(
                    ContextCompat.getColor(this@MainActivity, if (selectedHere) R.color.accent_dim else R.color.panel2)
                )
                setTextColor(ContextCompat.getColor(this@MainActivity, if (selectedHere) R.color.accent else R.color.white))
                setOnClickListener { action() }
            }
            row.addView(button, LinearLayout.LayoutParams(0, dp(52), 1f).apply {
                marginStart = dp(2)
                marginEnd = dp(2)
            })
        }
        add("RIDE", selected == Screen.ACTIVE) {
            if (rideStarted) showScreen(Screen.ACTIVE) else showScreen(Screen.HOME)
        }
        add("MAP", selected == Screen.MAP) {
            if (!rideStarted) {
                Toast.makeText(this, "Start a RideMesh ride to use the live group map.", Toast.LENGTH_SHORT).show()
            } else {
                showScreen(Screen.MAP)
            }
        }
        add("RIDERS", false) { showRidersDialog() }
        add("SETTINGS", false) { showSettingsAndHelpDialog() }
        return row
    }

    private fun beginLiveMapSession() {
        riderLocations.clear()
        myLiveLocation = null
        selectedMapRiderId = null
        lastLocationPublishMs = 0L
        lastPublishedLocation = null
        updateLiveMapHeader()
        ensureLocationSharingPermission(promptIfMissing = true)
    }

    private fun endLiveMapSession() {
        stopLiveLocationSharing()
        riderLocations.clear()
        myLiveLocation = null
        selectedMapRiderId = null
        riderMapMarkers.values.forEach { runCatching { it.remove() } }
        riderMapMarkers.clear()
        liveMap?.clear()
        liveMapVisible = false
        liveMapScreen?.visibility = View.GONE
    }

    private fun hasLocationPermission(): Boolean =
        ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED

    private fun ensureLocationSharingPermission(promptIfMissing: Boolean = true) {
        if (!rideStarted) return
        if (hasLocationPermission()) {
            startRideServiceSafely()
            startLiveLocationSharing()
            return
        }
        liveMapStatus?.text = "LOCATION PERMISSION NEEDED • VOICE ACTIVE"
        if (promptIfMissing) {
            locationPermissionLauncher.launch(
                arrayOf(Manifest.permission.ACCESS_COARSE_LOCATION, Manifest.permission.ACCESS_FINE_LOCATION)
            )
        }
    }

    @android.annotation.SuppressLint("MissingPermission")
    private fun startLiveLocationSharing() {
        if (!rideStarted || !hasLocationPermission() || liveLocationCallback != null) return
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, LOCATION_GPS_INTERVAL_MS)
            .setMinUpdateIntervalMillis(LOCATION_GPS_MIN_INTERVAL_MS)
            .setMinUpdateDistanceMeters(2f)
            .setMaxUpdateDelayMillis(LOCATION_GPS_MAX_DELAY_MS)
            .build()
        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val location = result.lastLocation ?: return
                handleLocalRideLocation(location)
            }
        }
        liveLocationCallback = callback
        runCatching {
            fusedLocationClient?.requestLocationUpdates(request, callback, Looper.getMainLooper())
        }.onFailure {
            liveLocationCallback = null
            liveMapStatus?.text = "GPS UNAVAILABLE • VOICE ACTIVE"
        }
    }

    private fun stopLiveLocationSharing() {
        liveLocationCallback?.let { callback ->
            runCatching { fusedLocationClient?.removeLocationUpdates(callback) }
        }
        liveLocationCallback = null
        lastPublishedLocation = null
        lastLocationPublishMs = 0L
    }

    private fun handleLocalRideLocation(location: Location) {
        if (!rideStarted) return
        val speedKmh = if (location.hasSpeed()) (location.speed * 3.6f).coerceAtLeast(0f) else 0f
        val heading = if (location.hasBearing()) location.bearing else 0f
        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val phone = prefs.getString(RIDER_PHONE_KEY, "").orEmpty()
        val snapshot = InternetNode.RiderLocation(
            riderId = internetNode.localRiderId(),
            displayName = rider,
            latitude = location.latitude,
            longitude = location.longitude,
            speedKmh = speedKmh,
            heading = heading,
            timestampMs = System.currentTimeMillis(),
            connectionQuality = internetNode.currentConnectionQualityLabel(),
            phoneNumber = phone,
        )
        myLiveLocation = snapshot

        val now = System.currentTimeMillis()
        if (shouldPublishRideLocation(location, speedKmh, now) &&
            internetNode.publishRiderLocation(location.latitude, location.longitude, speedKmh, heading, phone)
        ) {
            lastLocationPublishMs = now
            lastPublishedLocation = Location(location)
        }

        if (liveMapVisible) renderLiveRiderMap(fitGroup = false)
    }

    private fun shouldPublishRideLocation(location: Location, speedKmh: Float, now: Long): Boolean {
        if (!internetNode.isConnected()) return false
        if (lastLocationPublishMs == 0L) return true
        val quality = internetNode.currentConnectionQualityLabel()
        val interval = when {
            quality.equals("Reconnecting", true) -> 6_000L
            quality.equals("Poor", true) -> 4_000L
            speedKmh < 3f -> 5_000L
            !appInForeground -> 3_000L
            binding.batterySaver.isChecked -> 1_800L
            else -> 1_000L
        }
        val elapsed = now - lastLocationPublishMs
        if (elapsed >= interval) return true
        val previous = lastPublishedLocation ?: return false
        val moved = previous.distanceTo(location)
        return moved >= 35f && elapsed >= 750L
    }

    private fun updateLiveMapHeader() {
        if (!::internetNode.isInitialized) return
        val total = if (rideStarted) internetNode.remotePeerCount() + 1 else 0
        liveMapStatus?.text = if (rideStarted) "● LIVE • $total RIDER${if (total == 1) "" else "S"}" else "MAP OFFLINE"
        liveMapShareStatus?.text = if (rideStarted && hasLocationPermission()) {
            "Location shared with $total rider${if (total == 1) "" else "s"} • Active ride only"
        } else if (rideStarted) {
            "Location not shared • Enable permission to appear on the group map"
        } else {
            "Location sharing stops automatically when the ride ends"
        }
    }

    private fun mapsApiKeyConfigured(): Boolean = runCatching {
        val info = packageManager.getApplicationInfo(packageName, PackageManager.GET_META_DATA)
        info.metaData?.getString("com.google.android.geo.API_KEY").orEmpty().isNotBlank()
    }.getOrDefault(false)

    private fun ensureGoogleMapReady() {
        if (liveMap != null) return
        val host = liveMapHost ?: return
        if (!mapsApiKeyConfigured()) {
            host.removeAllViews()
            host.addView(TextView(this).apply {
                gravity = Gravity.CENTER
                text = "GOOGLE MAPS KEY REQUIRED\nVoice and rider location sharing remain available."
                textSize = 14f
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
            }, FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
            return
        }
        val tag = LIVE_MAP_FRAGMENT_TAG
        val fragment = supportFragmentManager.findFragmentByTag(tag) as? SupportMapFragment
            ?: SupportMapFragment.newInstance()
        if (!fragment.isAdded) {
            supportFragmentManager.beginTransaction().replace(host.id, fragment, tag).commitNowAllowingStateLoss()
        }
        fragment.getMapAsync { map ->
            liveMap = map
            map.uiSettings.apply {
                isCompassEnabled = true
                isMapToolbarEnabled = false
                isZoomControlsEnabled = false
                isMyLocationButtonEnabled = false
                isIndoorLevelPickerEnabled = false
            }
            runCatching { map.setMapStyle(MapStyleOptions(DARK_MAP_STYLE_JSON)) }
            map.setOnMarkerClickListener { marker ->
                val riderId = marker.tag as? String ?: return@setOnMarkerClickListener false
                val mine = myLiveLocation?.riderId?.toString()
                if (riderId == mine) {
                    Toast.makeText(this, "This is your live position.", Toast.LENGTH_SHORT).show()
                } else {
                    selectedMapRiderId = riderId
                    riderLocations[riderId]?.let(::showLiveRiderCard)
                    renderLiveRiderMap(fitGroup = false)
                }
                true
            }
            renderLiveRiderMap(fitGroup = true)
        }
    }

    private fun renderLiveRiderMap(fitGroup: Boolean) {
        val map = liveMap ?: return
        val mine = myLiveLocation
        val now = System.currentTimeMillis()
        val all = buildList {
            mine?.let { add(it) }
            addAll(riderLocations.values.sortedBy { it.displayName.lowercase(Locale.ROOT) })
        }
        if (all.isEmpty()) return

        val peerQuality = internetNode.remotePeers().associateBy({ it.id.toString() }, { it.qualityLabel })
        val visibleIds = mutableSetOf<String>()
        all.forEach { location ->
            val id = location.riderId.toString()
            visibleIds += id
            val self = mine?.riderId == location.riderId
            val age = (now - location.timestampMs).coerceAtLeast(0L)
            val quality = if (self) "You" else peerQuality[id] ?: location.connectionQuality
            val offline = !self && age >= MAP_OFFLINE_AFTER_MS
            val selected = selectedMapRiderId == id
            val statusColor = markerStatusColor(self, selected, quality, offline, age)
            val distance = if (self || mine == null) null else distanceMeters(mine, location)
            val markerPosition = LatLng(location.latitude, location.longitude)
            val icon = BitmapDescriptorFactory.fromBitmap(
                createRiderMarkerBitmap(
                    name = if (self) "YOU" else location.displayName.ifBlank { "RIDER" },
                    speedKmh = location.speedKmh,
                    distanceMeters = distance,
                    heading = location.heading,
                    statusColor = statusColor,
                    stale = offline,
                )
            )
            val marker = riderMapMarkers[id]
            if (marker == null) {
                riderMapMarkers[id] = map.addMarker(
                    MarkerOptions().position(markerPosition).icon(icon).anchor(0.5f, 1f).zIndex(if (self) 5f else 3f)
                )!!.apply { tag = id }
            } else {
                marker.position = markerPosition
                marker.setIcon(icon)
                marker.tag = id
            }
        }

        riderMapMarkers.keys.filter { it !in visibleIds }.toList().forEach { id ->
            riderMapMarkers.remove(id)?.remove()
        }

        if (fitGroup && now - lastMapFitMs >= MAP_AUTO_FIT_COOLDOWN_MS) {
            fitMapToRiders(all)
            lastMapFitMs = now
        }
    }

    private fun fitMapToRiders(locations: List<InternetNode.RiderLocation>) {
        val map = liveMap ?: return
        if (locations.isEmpty()) return
        if (locations.size == 1) {
            val one = locations.first()
            map.animateCamera(CameraUpdateFactory.newLatLngZoom(LatLng(one.latitude, one.longitude), 15.5f))
            return
        }
        val bounds = LatLngBounds.Builder()
        locations.forEach { bounds.include(LatLng(it.latitude, it.longitude)) }
        runCatching {
            map.animateCamera(CameraUpdateFactory.newLatLngBounds(bounds.build(), dp(64)))
        }
    }

    private fun markerStatusColor(self: Boolean, selected: Boolean, quality: String, offline: Boolean, ageMs: Long): Int {
        if (self || selected) return Color.parseColor("#00E5FF")
        if (offline) return Color.parseColor("#7E8588")
        if (ageMs >= MAP_WEAK_AFTER_MS) return Color.parseColor("#FFB020")
        return when (quality.lowercase(Locale.ROOT)) {
            "excellent", "good" -> Color.parseColor("#37D67A")
            "poor" -> Color.parseColor("#FF453A")
            "reconnecting" -> Color.parseColor("#FF453A")
            "fair", "weak" -> Color.parseColor("#FFB020")
            else -> Color.parseColor("#FFB020")
        }
    }

    private fun createRiderMarkerBitmap(
        name: String,
        speedKmh: Float,
        distanceMeters: Float?,
        heading: Float,
        statusColor: Int,
        stale: Boolean,
    ): Bitmap {
        val width = dp(176)
        val height = dp(92)
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#E6070C0C") }
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = statusColor
            style = Paint.Style.STROKE
            strokeWidth = dp(2).toFloat()
        }
        val rect = RectF(dp(2).toFloat(), dp(2).toFloat(), (width - dp(2)).toFloat(), (height - dp(12)).toFloat())
        canvas.drawRoundRect(rect, dp(14).toFloat(), dp(14).toFloat(), bg)
        canvas.drawRoundRect(rect, dp(14).toFloat(), dp(14).toFloat(), stroke)

        val dot = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = statusColor; style = Paint.Style.FILL }
        canvas.drawCircle(dp(19).toFloat(), dp(22).toFloat(), dp(7).toFloat(), dot)
        val arrow = Path().apply {
            moveTo(dp(19).toFloat(), dp(11).toFloat())
            lineTo(dp(13).toFloat(), dp(27).toFloat())
            lineTo(dp(19).toFloat(), dp(24).toFloat())
            lineTo(dp(25).toFloat(), dp(27).toFloat())
            close()
        }
        canvas.save()
        canvas.rotate(heading, dp(19).toFloat(), dp(22).toFloat())
        canvas.drawPath(arrow, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE })
        canvas.restore()

        val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = dp(14).toFloat()
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val infoPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#D7E1E0")
            textSize = dp(11).toFloat()
        }
        val clippedName = name.uppercase(Locale.ROOT).take(18)
        canvas.drawText(clippedName, dp(34).toFloat(), dp(27).toFloat(), titlePaint)
        canvas.drawText("${speedKmh.roundToInt()} km/h", dp(14).toFloat(), dp(50).toFloat(), infoPaint)
        val distanceText = if (distanceMeters == null) "YOUR POSITION" else formatMapDistance(distanceMeters).uppercase(Locale.ROOT)
        canvas.drawText(distanceText, dp(14).toFloat(), dp(68).toFloat(), infoPaint)
        if (stale) {
            canvas.drawText("LAST KNOWN", dp(104).toFloat(), dp(50).toFloat(), Paint(infoPaint).apply { color = statusColor })
        }
        return bitmap
    }

    private fun distanceMeters(a: InternetNode.RiderLocation, b: InternetNode.RiderLocation): Float {
        val out = FloatArray(1)
        Location.distanceBetween(a.latitude, a.longitude, b.latitude, b.longitude, out)
        return out[0].coerceAtLeast(0f)
    }

    private fun formatMapDistance(meters: Float): String = when {
        meters < 1000f -> "${meters.roundToInt()} m from you"
        meters < 10_000f -> String.format(Locale.US, "%.1f km from you", meters / 1000f)
        else -> "${(meters / 1000f).roundToInt()} km from you"
    }

    private fun formatLastUpdate(timestampMs: Long): String {
        val seconds = ((System.currentTimeMillis() - timestampMs).coerceAtLeast(0L) / 1000L)
        return when {
            seconds <= 2L -> "Now"
            seconds < 60L -> "$seconds sec ago"
            else -> "${seconds / 60L} min ago"
        }
    }

    private fun showLiveRiderCard(location: InternetNode.RiderLocation) {
        val mine = myLiveLocation
        val distance = mine?.let { distanceMeters(it, location) }
        val peer = internetNode.remotePeers().firstOrNull { it.id == location.riderId }
        val age = System.currentTimeMillis() - location.timestampMs
        val connection = if (age >= MAP_OFFLINE_AFTER_MS) "Last known position" else peer?.qualityLabel ?: location.connectionQuality
        showRideMeshPanel(location.displayName.ifBlank { "RIDER" }.uppercase(Locale.ROOT), "Live group awareness • No internal navigation") { body, _ ->
            addPanelInfo(body, "Speed", "${location.speedKmh.roundToInt()} km/h", highlight = true)
            addPanelInfo(body, "Distance", distance?.let(::formatMapDistance) ?: "Waiting for your GPS")
            addPanelInfo(body, "Connection", connection)
            addPanelInfo(body, "Last update", formatLastUpdate(location.timestampMs))
            val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            actions.addView(mapActionButton("NAVIGATE") { openExternalNavigation(location) }, LinearLayout.LayoutParams(0, dp(52), 1f))
            actions.addView(mapActionButton("CALL") { openRiderDialer(location.phoneNumber) }, LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginStart = dp(5); marginEnd = dp(5) })
            actions.addView(mapActionButton("MESSAGE") { openRiderMessage(location.phoneNumber) }, LinearLayout.LayoutParams(0, dp(52), 1f))
            body.addView(actions, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(54)).apply { topMargin = dp(6) })
        }
    }

    private fun mapActionButton(label: String, action: () -> Unit): MaterialButton = MaterialButton(this).apply {
        text = label
        textSize = 9.5f
        setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        cornerRadius = dp(12)
        strokeWidth = dp(1)
        strokeColor = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.accent))
        backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.panel2))
        setTextColor(ContextCompat.getColor(this@MainActivity, R.color.accent))
        setOnClickListener { action() }
    }

    private fun openExternalNavigation(location: InternetNode.RiderLocation) {
        val coordinates = "${location.latitude},${location.longitude}"
        val appIntent = Intent(Intent.ACTION_VIEW, Uri.parse("google.navigation:q=$coordinates")).apply {
            setPackage("com.google.android.apps.maps")
        }
        try {
            startActivity(appIntent)
        } catch (_: ActivityNotFoundException) {
            val browser = Intent(
                Intent.ACTION_VIEW,
                Uri.parse("https://www.google.com/maps/dir/?api=1&destination=${Uri.encode(coordinates)}")
            )
            startActivity(browser)
        }
    }

    private fun openRiderDialer(phone: String) {
        val safe = normalizeRiderPhone(phone)
        if (safe.isBlank()) {
            Toast.makeText(this, "This rider has not shared a phone number.", Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(Intent.ACTION_DIAL, Uri.parse("tel:$safe")))
    }

    private fun openRiderMessage(phone: String) {
        val safe = normalizeRiderPhone(phone)
        if (safe.isBlank()) {
            Toast.makeText(this, "This rider has not shared a phone number.", Toast.LENGTH_SHORT).show()
            return
        }
        startActivity(Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:$safe")))
    }

'''
    s = s[:idx] + helpers + s[idx:]

if 'RIDER_PHONE_KEY' not in s[s.rfind('companion object'):]:
    anchor = '    companion object {\n'
    constants = r'''    companion object {
        private const val RIDER_PHONE_KEY = "rider_phone"
        private const val LIVE_MAP_FRAGMENT_TAG = "ridemesh_live_rider_map"
        private const val LOCATION_GPS_INTERVAL_MS = 1_000L
        private const val LOCATION_GPS_MIN_INTERVAL_MS = 750L
        private const val LOCATION_GPS_MAX_DELAY_MS = 1_500L
        private const val MAP_WEAK_AFTER_MS = 6_000L
        private const val MAP_OFFLINE_AFTER_MS = 15_000L
        private const val MAP_AUTO_FIT_COOLDOWN_MS = 5_000L
        private val DARK_MAP_STYLE_JSON = """
            [
              {"elementType":"geometry","stylers":[{"color":"#08100f"}]},
              {"elementType":"labels.text.fill","stylers":[{"color":"#8fa3a1"}]},
              {"elementType":"labels.text.stroke","stylers":[{"color":"#08100f"}]},
              {"featureType":"administrative","elementType":"geometry","stylers":[{"color":"#20302e"}]},
              {"featureType":"poi","stylers":[{"visibility":"off"}]},
              {"featureType":"road","elementType":"geometry","stylers":[{"color":"#172321"}]},
              {"featureType":"road","elementType":"geometry.stroke","stylers":[{"color":"#101817"}]},
              {"featureType":"road.highway","elementType":"geometry","stylers":[{"color":"#203633"}]},
              {"featureType":"transit","stylers":[{"visibility":"off"}]},
              {"featureType":"water","elementType":"geometry","stylers":[{"color":"#061b22"}]}
            ]
        """.trimIndent()
'''
    s = replace_once(s, anchor, constants, 'map constants')

p.write_text(s)


# -----------------------------------------------------------------------------
# Unit test: cross-platform location packet contract round-trip.
# -----------------------------------------------------------------------------
p = ROOT / 'app/src/test/java/com/bikemesh/ridemesh/transport/InternetNodeTest.kt'
s = p.read_text()
if 'locationPacketRoundTripsForAndroidIosProtocol' not in s:
    insert = r'''
    @Test
    fun locationPacketRoundTripsForAndroidIosProtocol() {
        val node = InternetNode(listener)
        val id = UUID.fromString("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        val packet = InternetNode.RiderLocation(
            riderId = id,
            displayName = "Faizal",
            latitude = 10.5276,
            longitude = 76.2144,
            speedKmh = 72.5f,
            heading = 91.0f,
            timestampMs = 1_725_000_123_456L,
            connectionQuality = "Excellent",
            phoneNumber = "+91 98765 43210",
        )
        val encoded = node.encodeLocation(packet)
        val decoded = node.decodeLocation(encoded)
        assertNotNull(decoded)
        assertEquals(id, decoded!!.riderId)
        assertEquals("Faizal", decoded.displayName)
        assertEquals(packet.latitude, decoded.latitude, 0.000001)
        assertEquals(packet.longitude, decoded.longitude, 0.000001)
        assertEquals(packet.speedKmh.toDouble(), decoded.speedKmh.toDouble(), 0.01)
        assertEquals(packet.heading.toDouble(), decoded.heading.toDouble(), 0.01)
        assertEquals("Excellent", decoded.connectionQuality)
        assertEquals("+91 98765 43210", decoded.phoneNumber)
    }
'''
    s = s.rsplit('\n}', 1)[0] + insert + '\n}\n'
p.write_text(s)

print('Beta5.1 Live Rider Map applied: room-scoped GPS + Google Maps UI + external rider actions, vc19')
