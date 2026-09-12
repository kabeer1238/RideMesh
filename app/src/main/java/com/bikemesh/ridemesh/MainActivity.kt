package com.bikemesh.ridemesh

import android.Manifest
import android.app.AlertDialog
import android.app.Dialog
import android.bluetooth.BluetoothManager
import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.res.ColorStateList
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.location.Location
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.util.Patterns
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import androidx.core.graphics.ColorUtils
import androidx.core.widget.doAfterTextChanged
import com.bikemesh.ridemesh.audio.AudioEngine
import com.bikemesh.ridemesh.beta.BetaWindow
import com.bikemesh.ridemesh.billing.RideMeshBillingManager
import com.bikemesh.ridemesh.audio.AudioRoute
import com.bikemesh.ridemesh.databinding.ActivityMainBinding
import com.bikemesh.ridemesh.mesh.LobbyNode
import com.bikemesh.ridemesh.mesh.MeshNode
import com.bikemesh.ridemesh.service.RideService
import com.bikemesh.ridemesh.service.RideShutdownCoordinator
import com.bikemesh.ridemesh.transport.InternetNode
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.GoogleMap
import com.google.android.gms.maps.model.MapStyleOptions
import com.google.android.gms.maps.SupportMapFragment
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.LatLng
import com.google.android.gms.maps.model.LatLngBounds
import com.google.android.gms.maps.model.Marker
import com.google.android.gms.maps.model.MarkerOptions
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
import kotlin.math.roundToInt
import kotlin.random.Random

class MainActivity : AppCompatActivity(), MeshNode.Listener, LobbyNode.Listener, InternetNode.Listener {
    private lateinit var binding: ActivityMainBinding
    private lateinit var meshNode: MeshNode
    private lateinit var lobbyNode: LobbyNode
    private lateinit var internetNode: InternetNode
    private lateinit var audioEngine: AudioEngine
    private lateinit var billingManager: RideMeshBillingManager
    private var billingProduct: RideMeshBillingManager.SubscriptionDisplay? = null
    private var premiumEntryAction = PremiumEntryAction.NONE

    private val prefs by lazy { getSharedPreferences("ridemesh", MODE_PRIVATE) }
    private val nearbyButtons = linkedMapOf<String, MaterialButton>()
    private val mainHandler = Handler(Looper.getMainLooper())
    private val speakingUntilMs = ConcurrentHashMap<String, Long>()
    private val locationShareHeartbeat = object : Runnable {
        override fun run() {
            if (!rideStarted) return
            publishCachedLocalLocationIfDue(force = false)
            mainHandler.postDelayed(this, LOCATION_SHARE_HEARTBEAT_CHECK_MS)
        }
    }

    private val riderLocations = ConcurrentHashMap<String, InternetNode.RiderLocation>()
    private val riderMapMarkers = mutableMapOf<String, Marker>()
    private var myLiveLocation: InternetNode.RiderLocation? = null
    private var fusedLocationClient: FusedLocationProviderClient? = null
    private var liveLocationCallback: LocationCallback? = null
    private var liveMap: GoogleMap? = null
    private var liveMapScreen: LinearLayout? = null
    private var ridersScreen: LinearLayout? = null
    private var ridersList: LinearLayout? = null
    private var currentRiders: List<RiderTile> = emptyList()
    private var liveMapHost: FrameLayout? = null
    private var liveMapStatus: TextView? = null
    private var liveMapShareStatus: TextView? = null
    private var liveMapVisible = false
    private var appInForeground = true
    private var lastLocationPublishMs = 0L
    private var lastPublishedLocation: Location? = null
    private var lastMapFitMs = 0L
    private var lastMapRenderMs = 0L
    private var selectedMapRiderId: String? = null
    private val riderClusterMarkers = mutableMapOf<String, Marker>()
    private var expandedClusterIds: Set<String> = emptySet()
    private var activeRiderDetailDialog: Dialog? = null
    private var activeRiderSheetExpanded = false
    private val riderDetailAutoHideRunnable = Runnable { dismissLiveRiderDetail() }
    private val clusterAutoCollapseRunnable = Runnable {
        if (expandedClusterIds.isNotEmpty()) {
            expandedClusterIds = emptySet()
            if (liveMapVisible) renderLiveRiderMap(fitGroup = false)
        }
    }


    private var rideStarted = false
    private var pendingAction = PendingAction.NONE
    private var directPeerCount = 0
    private var internetPeerCount = 0
    private var meshRunning = false
    private var internetConnectedSinceMs = 0L
    private var lastMeshRefreshMs = 0L
    @Volatile private var micMuted = false
    private var betaExpiredDialogShown = false
    private var transportMode = TransportMode.AUTO
    private var meshLabRole = MeshNode.LabRole.NORMAL
    private var setupMode = SetupMode.CREATE

    private enum class TransportMode { AUTO, LOCAL_ONLY, INTERNET_ONLY }
    private enum class PendingAction { NONE, START_RIDE, FIND_RIDERS }
    private enum class Screen { HOME, SETUP, ACTIVE, MAP, RIDERS, PREMIUM }
    private enum class PremiumEntryAction { NONE, CREATE_RIDE, JOIN_RIDE, START_RIDE }
    private enum class SetupMode { CREATE, JOIN }

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

    private val locationPermissionLauncher = registerForActivityResult(
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        restoreSettings()
        binding.riderPhone.setText(prefs.getString(RIDER_PHONE_KEY, "").orEmpty())
        ensureBetaFirstLaunch()

        meshNode = MeshNode(applicationContext, this)
        lobbyNode = LobbyNode(applicationContext, this)
        internetNode = InternetNode(this, applicationContext)
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)

        audioEngine = AudioEngine(
            context = applicationContext,
            onCapturedFrame = ::sendHybridAudio,
            onStatus = { text -> runOnUiThread { updateAudioUi(text) } },
        )

        applySelectedAudioRoute()
        showScreen(Screen.HOME)
        clearNearbyRiders("Tap FIND to discover RideMesh riders nearby.")
        applyPowerUi()

        billingManager = RideMeshBillingManager(
            context = this,
            onEntitlementChanged = { active ->
                runOnUiThread {
                    if (active) continueAfterPremiumUnlock()
                }
            },
            onProductChanged = { product ->
                runOnUiThread {
                    billingProduct = product
                    renderPremiumPage()
                }
            },
            onBillingMessage = { message ->
                runOnUiThread { android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show() }
            },
        )
        billingManager.start()

        installRideMainNavigation()

        binding.createRide.setOnClickListener {
            if (!ensureBetaUsable()) return@setOnClickListener
            if (!ensurePremiumAccess()) return@setOnClickListener
            setupMode = SetupMode.CREATE
            binding.setupTitle.text = "CREATE RIDE"
            binding.startRide.text = "START RIDE"
            binding.rideCode.setText(generateRideCode())
            showScreen(Screen.SETUP)
        }

        binding.joinRide.setOnClickListener {
            if (!ensureBetaUsable()) return@setOnClickListener
            if (!ensurePremiumAccess()) return@setOnClickListener
            setupMode = SetupMode.JOIN
            binding.setupTitle.text = "JOIN RIDE"
            binding.startRide.text = "JOIN RIDE"
            showScreen(Screen.SETUP)
            binding.rideCode.requestFocus()
        }


        binding.premiumBack.setOnClickListener {
            premiumEntryAction = PremiumEntryAction.NONE
            showScreen(Screen.HOME)
        }
        binding.premiumPrimary.setOnClickListener {
            val product = billingProduct
            if (product == null) {
                billingManager.refresh()
            } else {
                billingManager.launchPurchase(this)
            }
        }
        binding.premiumRestore.setOnClickListener { billingManager.restorePurchases() }
        binding.premiumPrivacy.setOnClickListener {
            runCatching {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://autopilotindia.com/ridemesh-privacy-policy/")))
            }
        }
        binding.premiumTerms.setOnClickListener {
            runCatching {
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/about/play-terms/")))
            }
        }

        binding.backHome.setOnClickListener {
            stopLobbyDiscovery()
            showScreen(Screen.HOME)
        }

        binding.openSettings.setOnClickListener { showSettingsAndHelpDialog() }
        binding.activeTopSettings.setOnClickListener { showSettingsAndHelpDialog() }
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
        binding.activeVersion.text = appVersionLabel()
        updateMuteUi()
        binding.logView.visibility = View.GONE

        binding.emailSave.setOnClickListener { saveEmailProfile() }
        binding.rideCode.doAfterTextChanged { text ->
            val value = text?.toString().orEmpty().trim().uppercase().take(12)
            if (value.isNotBlank()) prefs.edit().putString("code", value).apply()
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // Rider requirement: Back never tears down an active voice session or exits the app.
                // The task moves to background; reopening returns to the same activity/ride state.
                moveTaskToBack(true)
            }
        })

        mainHandler.post { ensureUserEmail() }
    }

    private fun savedUserEmail(): String =
        prefs.getString(USER_EMAIL_KEY, "").orEmpty().trim()

    private fun hasValidUserEmail(): Boolean =
        Patterns.EMAIL_ADDRESS.matcher(savedUserEmail()).matches()

    private fun ensureUserEmail(): Boolean {
        if (hasValidUserEmail()) {
            binding.screenEmail.visibility = View.GONE
            return true
        }
        showEmailProfileScreen()
        return false
    }

    private fun showEmailProfileScreen() {
        binding.emailInput.setText(savedUserEmail())
        binding.emailInput.error = null
        binding.screenEmail.visibility = View.VISIBLE
        binding.emailInput.requestFocus()
    }

    private fun riderNameFromEmail(email: String): String {
        val local = email.substringBefore('@')
            .replace('.', ' ')
            .replace('_', ' ')
            .replace('-', ' ')
            .trim()
        val words = local.split(' ').filter { it.isNotBlank() }
        val display = words.joinToString(" ") { word ->
            word.lowercase(Locale.ROOT).replaceFirstChar { ch ->
                if (ch.isLowerCase()) ch.titlecase(Locale.ROOT) else ch.toString()
            }
        }.trim()
        return display.ifBlank { "Rider" }.take(24)
    }

    private fun saveEmailProfile() {
        val email = binding.emailInput.text?.toString().orEmpty().trim().lowercase()
        if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {
            binding.emailInput.error = "Enter a valid email address"
            binding.emailInput.requestFocus()
            return
        }

        val currentName = binding.riderName.text?.toString().orEmpty().trim()
        val storedName = prefs.getString("rider", "").orEmpty().trim()
        val shouldCreateName = currentName.isBlank() || currentName.equals("Rider", true) || storedName.isBlank() || storedName.equals("Rider", true)
        val editor = prefs.edit().putString(USER_EMAIL_KEY, email)
        if (shouldCreateName) {
            val generatedName = riderNameFromEmail(email)
            binding.riderName.setText(generatedName)
            editor.putString("rider", generatedName)
        }
        editor.apply()
        binding.screenEmail.visibility = View.GONE
    }

    private fun showScreen(screen: Screen) {
        binding.screenHome.visibility = if (screen == Screen.HOME) View.VISIBLE else View.GONE
        binding.screenSetup.visibility = if (screen == Screen.SETUP) View.VISIBLE else View.GONE
        binding.screenActive.visibility = if (screen == Screen.ACTIVE) View.VISIBLE else View.GONE
        binding.screenPremium.visibility = if (screen == Screen.PREMIUM) View.VISIBLE else View.GONE
        ridersScreen?.visibility = if (screen == Screen.RIDERS) View.VISIBLE else View.GONE
        liveMapVisible = screen == Screen.MAP
        liveMapScreen?.visibility = if (liveMapVisible) View.VISIBLE else View.GONE
        if (liveMapVisible) {
            ensureLocationSharingPermission()
            ensureGoogleMapReady()
            updateLiveMapHeader()
            renderLiveRiderMap(fitGroup = true)
        }
    }

    private fun ensurePermissionsAndRun(action: PendingAction) {
        if (action == PendingAction.START_RIDE && !ensureBetaUsable()) return
        if (action == PendingAction.START_RIDE && !ensurePremiumAccess()) return
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
        val code = validatedRideCodeOrNull() ?: return
        showRideMeshPanel(
            "INVITE RIDERS",
            "Share this Ride Code or QR. Riders use Join a Ride and the same code to enter your group.",
        ) { body, dialog ->
            addPanelSection(body, "Ride code")
            addPanelInfo(body, "Current code", code, highlight = true)
            addPanelButton(body, "SHOW QR CODE") {
                dialog.dismiss()
                showRideQr()
            }
            addPanelButton(body, "SHARE QR CODE", primary = false) {
                dialog.dismiss()
                shareRideQr()
            }
        }
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
        val code = validatedRideCodeOrNull() ?: return
        binding.rideCode.setText(code)
        saveSettings()

        try {
            val bitmap = buildRideQrBitmap(code)
            showRideMeshPanel("RIDE QR", "Scan to join RideMesh ride $code.") { body, dialog ->
                addPanelInfo(body, "Ride code", code, highlight = true)
                val image = ImageView(this).apply {
                    setImageBitmap(bitmap)
                    adjustViewBounds = true
                    setPadding(dp(12), dp(12), dp(12), dp(12))
                    background = panelCardBackground()
                }
                body.addView(image, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                    topMargin = dp(6)
                    bottomMargin = dp(8)
                })
                addPanelButton(body, "SHARE QR") {
                    dialog.dismiss()
                    shareRideQr()
                }
            }
        } catch (t: Throwable) {
            log("Could not create QR: ${t.message ?: t.javaClass.simpleName}")
        }
    }

    private fun shareRideQr() {
        val code = validatedRideCodeOrNull() ?: return
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

                setupMode = SetupMode.JOIN
                binding.setupTitle.text = "JOIN RIDE"
                binding.startRide.text = "JOIN RIDE"
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
            ?.take(12)
            ?.takeIf(::isValidRideCode)
    }.getOrNull()

    private fun startRideNow() {
        if (rideStarted || !ensureBetaUsable()) return
        if (!ensureUserEmail()) return

        val code = normalizedRideCode()
        if (!isValidRideCode(code)) {
            binding.rideCode.error = "Use 5–12 letters and numbers only"
            binding.rideCode.requestFocus()
            return
        }

        if (transportMode == TransportMode.LOCAL_ONLY && !radiosReady()) {
            AlertDialog.Builder(this).setMessage("Turn on Wi-Fi and Bluetooth. Mobile data can stay off for offline mesh.")
                .setPositiveButton("OK", null).show()
            return
        }
        setMicMuted(false)
        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        binding.riderName.setText(rider)
        binding.rideCode.setText(code)
        val ridePhone = normalizeRiderPhone(binding.riderPhone.text?.toString().orEmpty())
        binding.riderPhone.setText(ridePhone)
        prefs.edit().putString(RIDER_PHONE_KEY, ridePhone).apply()
        saveSettings()

        try {
            stopLobbyDiscovery()

            rideStarted = true
            directPeerCount = 0
            internetPeerCount = 0
            meshRunning = false
            internetConnectedSinceMs = 0L
            lastMeshRefreshMs = 0L

            // Initialize voice first. If a device rejects audio/WebRTC initialization, the
            // existing recovery path keeps the Activity alive instead of leaving an FGS behind.
            if (transportMode == TransportMode.LOCAL_ONLY) {
                audioEngine.packetDecoder = meshNode::decodeForPlayout
                ensureLocalMeshRunning("offline six-rider test")
            } else {
                audioEngine.packetDecoder = null
                internetNode.start(code, rider, deviceLabel())
                internetNode.setMuted(micMuted)
            }
            applySelectedAudioRoute()
            beginLiveMapSession()
            RideShutdownCoordinator.register(::shutdownRideRuntimeFromTaskRemoval)

            // Start the foreground ride service only after media initialization succeeds.
            startRideServiceSafely()

            binding.activeRideCode.text = code
            showScreen(Screen.ACTIVE)
            updateTransportStatus()
            updateCapturePolicy()

            mainHandler.removeCallbacks(rideWatchdog)
            mainHandler.postDelayed(rideWatchdog, WATCHDOG_INTERVAL_MS)
            log("Ride started • ${transportModeLabel()} • build 32")
        } catch (t: Throwable) {
            recoverFromStartFailure(t)
        }
    }

    private fun sendHybridAudio(audio: ByteArray) {
        if (rideStarted && transportMode == TransportMode.LOCAL_ONLY && !micMuted) meshNode.sendLocalAudio(audio)
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
        if (transportMode == TransportMode.LOCAL_ONLY) {
            audioEngine.setUserMuted(micMuted)
            audioEngine.startTransmit()
            updateAudioUi(if (micMuted) "MIC MUTED • LISTENING ONLY" else "OFFLINE OPUS • $directPeerCount DIRECT LINKS")
            return
        }
        val status = when {
            micMuted -> "MIC MUTED • LISTENING ONLY"
            internetNode.voicePeerCount() > 0 -> "VOICE CONNECTED • MIC LIVE"
            internetNode.isConnected() -> "VOICE READY • WAITING FOR RIDERS"
            else -> "CONNECTING • MIC READY"
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
        runCatching { endLiveMapSession() }
        runCatching { internetNode.stop() }
        runCatching { meshNode.stop() }
        RideShutdownCoordinator.clear()
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
            .setPositiveButton("REPORT BUG") { _, _ -> openEmailSupport() }
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
        endLiveMapSession()
        internetNode.stop()
        meshRunning = false
        meshNode.stop()
        stopService(Intent(this, RideService::class.java))
        RideShutdownCoordinator.clear()

        rideStarted = false
        directPeerCount = 0
        internetPeerCount = 0
        internetConnectedSinceMs = 0L
        binding.riderCount.text = android.text.SpannableString("RIDE ACTIVE").apply { setSpan(android.text.style.ForegroundColorSpan(ContextCompat.getColor(this@MainActivity, R.color.accent)), 5, 11, 0) }
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
        if (transportMode == TransportMode.LOCAL_ONLY && ::audioEngine.isInitialized) {
            audioEngine.setRoute(com.bikemesh.ridemesh.audio.AudioRoute.valueOf(route))
            return
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
        if (::audioEngine.isInitialized) audioEngine.setUserMuted(muted)
        if (::binding.isInitialized) {
            updateMuteUi()
            renderRiderGrid()
        }
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
        transportMode = if (prefs.getString("transport_mode", "LOCAL_ONLY") == "INTERNET_ONLY")
            TransportMode.INTERNET_ONLY else TransportMode.LOCAL_ONLY
        meshLabRole = runCatching {
            MeshNode.LabRole.valueOf(prefs.getString("mesh_lab_role", "NORMAL") ?: "NORMAL")
        }.getOrDefault(MeshNode.LabRole.NORMAL)

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
        .take(12)

    private fun isValidRideCode(code: String): Boolean =
        code.length in 5..12 && code.all { it in 'A'..'Z' || it in '0'..'9' }

    private fun validatedRideCodeOrNull(): String? {
        val code = normalizedRideCode()
        if (isValidRideCode(code)) return code
        binding.rideCode.error = "Use 5–12 letters and numbers only"
        binding.rideCode.requestFocus()
        return null
    }

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
        if (transportMode != TransportMode.INTERNET_ONLY) {
            add(Manifest.permission.ACCESS_FINE_LOCATION)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                add(Manifest.permission.BLUETOOTH_SCAN)
                add(Manifest.permission.BLUETOOTH_ADVERTISE)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) add(Manifest.permission.NEARBY_WIFI_DEVICES)
        }
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
        if (connected && rideStarted) publishCachedLocalLocationIfDue(force = true)
        runOnUiThread {
            log(message)
            internetConnectedSinceMs = if (connected) System.currentTimeMillis() else 0L
            updateTransportStatus()
            updateCapturePolicy()
        }
    }

    override fun onInternetPeerCount(count: Int) {
        val previousCount = internetPeerCount
        internetPeerCount = count
        if (rideStarted && count > previousCount) publishCachedLocalLocationIfDue(force = true)
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

    override fun onInternetRiderLocation(location: InternetNode.RiderLocation) {
        if (!rideStarted) return
        val riderId = location.riderId.toString()
        val firstLocationFromRider = riderLocations.put(riderId, location) == null
        runOnUiThread {
            updateLiveMapHeader()
            if (liveMapVisible) {
                if (firstLocationFromRider) lastMapFitMs = 0L
                renderLiveRiderMap(fitGroup = firstLocationFromRider)
            }
        }
    }

    private fun updateTransportStatus() {
        if (!rideStarted) return
        if (transportMode == TransportMode.LOCAL_ONLY) {
            val mesh = meshNode.diagnostics()
            binding.networkTile.text = "OFFLINE"
            binding.riderCount.text = "OFFLINE TEST"
            binding.meshStatus.text = "●  ${mesh.reachableRiders} RIDERS • ${mesh.directPeers} DIRECT • MAX ${mesh.maxObservedHops} HOPS"
            binding.homeNetworkStatus.text = "Offline\nMesh"
            binding.activeRiders.text = "RIDERS"
            renderRiderGrid()
            return
        }
        val diag = internetNode.diagnostics()

        binding.networkTile.text = when {
            diag.voicePeersConnected > 0 -> "CONNECTED"
            diag.signalingConnected -> "READY"
            else -> "CONNECTING"
        }
        binding.riderCount.text = android.text.SpannableString("RIDE ACTIVE").apply { setSpan(android.text.style.ForegroundColorSpan(ContextCompat.getColor(this@MainActivity, R.color.accent)), 5, 11, 0) }
        binding.meshStatus.text = when {
            diag.voicePeersConnected > 0 ->
                "●  CONNECTED • LIVE • ${diag.voicePeersConnected + 1} RIDERS"
            diag.signalingConnected -> "●  CONNECTED • READY"
            else -> "●  RECONNECTING…"
        }
        binding.homeNetworkStatus.text = when {
            diag.voicePeersConnected > 0 -> "Voice\nConnected"
            diag.signalingConnected -> "Internet\nReady"
            else -> "Connection\nReady"
        }

        val visibleRiderTotal = if (internetNode.isConnected()) internetPeerCount + 1 else 1
        binding.activeRiders.text = "RIDERS"
        renderRiderGrid()
        updateLiveMapHeader()
        if (liveMapVisible) renderLiveRiderMap(fitGroup = false)
        applyPowerUi()
    }

    private fun markRiderSpeaking(key: String) {
        val now = System.currentTimeMillis()
        if ((speakingUntilMs[key] ?: 0L) > now + SPEAKING_HOLD_MS - 200L) return
        val expires = now + SPEAKING_HOLD_MS
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
            meshNode.reachablePeers().forEach { peer ->
                riders += RiderTile(
                    key = peer.endpointId,
                    name = peer.displayName,
                    device = peer.deviceName,
                    qualityBars = peer.qualityBars,
                    path = if (peer.hopCount == 1) "Direct offline" else "Relayed • ${peer.hopCount} hops",
                )
            }
        }

        currentRiders = riders.toList()
        renderRidersScreen()
        val visible = riders.take(3)
        val grid = binding.riderGrid
        grid.removeAllViews()
        grid.columnCount = 1
        grid.rowCount = visible.size.coerceAtLeast(1)

        visible.forEachIndexed { index, rider ->
            grid.addView(buildRiderTile(rider), GridLayout.LayoutParams().apply {
                rowSpec = GridLayout.spec(index)
                columnSpec = GridLayout.spec(0, 1f)
                width = 0
                height = dp(72)
                setMargins(0, dp(4), 0, dp(4))
            })
        }
    }

    private fun buildRiderTile(rider: RiderTile): View {
        val speaking = (speakingUntilMs[rider.key] ?: 0L) > System.currentTimeMillis()
        val accent = ContextCompat.getColor(this, R.color.accent)
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(10), dp(8), dp(10), dp(8))
            background = GradientDrawable().apply {
                cornerRadius = dp(14).toFloat()
                setColor(Color.parseColor(if (speaking) "#0B1B19" else "#070C0C"))
                setStroke(dp(if (speaking) 2 else 1), if (speaking) accent else ContextCompat.getColor(this@MainActivity, R.color.border))
            }
        }

        val avatar = ImageView(this).apply {
            setImageResource(R.drawable.rm_helmet_avatar)
            contentDescription = "Rider helmet"
            setPadding(dp(5), dp(5), dp(5), dp(5))
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#031217"))
                setStroke(dp(1), accent)
            }
        }
        card.addView(avatar, LinearLayout.LayoutParams(dp(48), dp(48)))

        val textBox = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
        }
        textBox.addView(TextView(this).apply {
            text = rider.name.ifBlank { "Rider" }
            maxLines = 1
            ellipsize = android.text.TextUtils.TruncateAt.END
            textSize = 14f
            setTextColor(ContextCompat.getColor(this@MainActivity, if (speaking) R.color.accent else R.color.white))
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        })
        textBox.addView(TextView(this).apply {
            text = when {
                rider.path == "Searching" -> "CONNECTING"
                rider.self -> if (micMuted) "MUTED • YOU" else "LIVE • YOU"
                speaking -> "LIVE • SPEAKING"
                else -> "LIVE • CONNECTED"
            }
            textSize = 10f
            setTextColor(if (rider.self || speaking) accent else ContextCompat.getColor(this@MainActivity, R.color.muted))
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(3)
        })
        card.addView(textBox, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply {
            marginStart = dp(14)
        })

        card.addView(SignalBarsView(this, rider.qualityBars, qualityColor(rider.qualityBars)),
            LinearLayout.LayoutParams(dp(40), dp(36)))
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

    private fun installRideMainNavigation() {
        if (liveMapScreen != null) return

        binding.screenActive.addView(
            buildRideMainNav(Screen.ACTIVE),
            LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(74)).apply {
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

        screen.addView(buildRideMainNav(Screen.MAP), LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(74)))
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
            setPadding(dp(4), dp(4), dp(4), dp(4))
            background = GradientDrawable().apply {
                cornerRadius = dp(24).toFloat()
                setColor(Color.parseColor("#050A0A"))
                setStroke(dp(1), ContextCompat.getColor(this@MainActivity, R.color.border))
            }
        }
        fun add(label: String, iconRes: Int, selectedHere: Boolean, action: () -> Unit) {
            val button = MaterialButton(this).apply {
                text = label
                textSize = 9.5f
                setTypeface(Typeface.DEFAULT, Typeface.BOLD)
                cornerRadius = dp(18)
                strokeWidth = 0
                backgroundTintList = ColorStateList.valueOf(
                    Color.parseColor(if (selectedHere) "#003138" else "#050A0A")
                )
                setTextColor(ContextCompat.getColor(this@MainActivity, if (selectedHere) R.color.accent else R.color.muted))
                setIconResource(iconRes)
                iconTint = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, if (selectedHere) R.color.accent else R.color.muted))
                iconGravity = MaterialButton.ICON_GRAVITY_TOP
                iconSize = dp(22)
                iconPadding = dp(2)
                setOnClickListener { action() }
            }
            row.addView(button, LinearLayout.LayoutParams(0, dp(66), 1f).apply {
                marginStart = dp(1)
                marginEnd = dp(1)
            })
        }
        add("RIDE", R.drawable.ic_rm_ride, selected == Screen.ACTIVE) {
            if (rideStarted) showScreen(Screen.ACTIVE) else showScreen(Screen.HOME)
        }
        add("MAP", R.drawable.ic_rm_map, selected == Screen.MAP) {
            if (!rideStarted) {
                Toast.makeText(this, "Start a RideMesh ride to use the live group map.", Toast.LENGTH_SHORT).show()
            } else {
                showScreen(Screen.MAP)
            }
        }
        add("RIDERS", R.drawable.ic_rm_riders, selected == Screen.RIDERS) { showRidersDialog() }
        add("SETTINGS", R.drawable.ic_rm_settings, false) { showSettingsAndHelpDialog() }
        return row
    }

    private fun beginLiveMapSession() {
        riderLocations.clear()
        myLiveLocation = null
        selectedMapRiderId = null
        lastLocationPublishMs = 0L
        lastPublishedLocation = null
        updateLiveMapHeader()
        mainHandler.removeCallbacks(locationShareHeartbeat)
        mainHandler.post(locationShareHeartbeat)
        ensureLocationSharingPermission(promptIfMissing = true)
    }

    private fun endLiveMapSession() {
        mainHandler.removeCallbacks(locationShareHeartbeat)
        stopLiveLocationSharing()
        riderLocations.clear()
        myLiveLocation = null
        selectedMapRiderId = null
        riderMapMarkers.values.forEach { runCatching { it.remove() } }
        riderMapMarkers.clear()
        riderClusterMarkers.values.forEach { it.remove() }
        riderClusterMarkers.clear()
        expandedClusterIds = emptySet()
        dismissLiveRiderDetail()
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

    private fun publishCachedLocalLocationIfDue(force: Boolean) {
        if (!rideStarted || !hasLocationPermission()) return
        val snapshot = myLiveLocation ?: return
        val now = System.currentTimeMillis()
        if (!force && now - lastLocationPublishMs < LOCATION_STATIONARY_HEARTBEAT_MS) return
        val phone = prefs.getString(RIDER_PHONE_KEY, "").orEmpty()
        if (internetNode.publishRiderLocation(
                snapshot.latitude,
                snapshot.longitude,
                snapshot.speedKmh,
                snapshot.heading,
                phone,
            )
        ) {
            lastLocationPublishMs = now
        }
    }

    private fun shutdownRideRuntimeFromTaskRemoval() {
        if (!rideStarted) {
            RideShutdownCoordinator.clear()
            return
        }
        mainHandler.removeCallbacks(stopLobbyScan)
        mainHandler.removeCallbacks(rideWatchdog)
        mainHandler.removeCallbacks(locationShareHeartbeat)
        runCatching { stopLobbyDiscovery() }
        runCatching { audioEngine.stopTransmit() }
        runCatching { endLiveMapSession() }
        runCatching { internetNode.stop() }
        meshRunning = false
        runCatching { meshNode.stop() }
        rideStarted = false
        directPeerCount = 0
        internetPeerCount = 0
        internetConnectedSinceMs = 0L
        RideShutdownCoordinator.clear()
        runCatching { audioEngine.release() }
    }

    private fun updateLiveMapHeader() {
        if (!::internetNode.isInitialized) return
        val total = if (rideStarted) internetNode.remotePeerCount() + 1 else 0
        liveMapStatus?.text = if (rideStarted) "● LIVE • $total RIDER${if (total == 1) "" else "S"}" else "MAP OFFLINE"
        liveMapShareStatus?.text = if (rideStarted && hasLocationPermission()) {
            val positionsLive = riderLocations.size + if (myLiveLocation != null) 1 else 0
            "Location shared with $total rider${if (total == 1) "" else "s"} • $positionsLive position${if (positionsLive == 1) "" else "s"} live"
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
                val tagValue = marker.tag as? String ?: return@setOnMarkerClickListener false
                if (tagValue.startsWith("cluster:")) {
                    val ids = tagValue.removePrefix("cluster:")
                        .split(',')
                        .map { it.trim() }
                        .filter { it.isNotBlank() }
                        .toSet()
                    if (ids.isNotEmpty()) {
                        dismissLiveRiderDetail()
                        selectedMapRiderId = null
                        expandedClusterIds = ids
                        mainHandler.removeCallbacks(clusterAutoCollapseRunnable)
                        mainHandler.postDelayed(clusterAutoCollapseRunnable, MAP_CLUSTER_EXPAND_TIMEOUT_MS)
                        renderLiveRiderMap(fitGroup = false)
                    }
                    return@setOnMarkerClickListener true
                }

                val riderId = tagValue
                val mine = myLiveLocation?.riderId?.toString()
                if (riderId == mine) {
                    myLiveLocation?.let(::showLiveRiderCard)
                } else {
                    selectedMapRiderId = riderId
                    riderLocations[riderId]?.let(::showLiveRiderCard)
                }
                renderLiveRiderMap(fitGroup = false)
                true
            }

            map.setOnMapClickListener {
                dismissLiveRiderDetail()
                selectedMapRiderId = null
                if (expandedClusterIds.isNotEmpty()) {
                    expandedClusterIds = emptySet()
                    mainHandler.removeCallbacks(clusterAutoCollapseRunnable)
                }
                renderLiveRiderMap(fitGroup = false)
            }

            map.setOnCameraIdleListener {
                if (liveMapVisible) renderLiveRiderMap(fitGroup = false)
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

        val projection = map.projection
        val mineId = mine?.riderId?.toString()
        val peerQuality = internetNode.remotePeers().associateBy({ it.id.toString() }, { it.qualityLabel })
        val shownRiderIds = mutableSetOf<String>()
        val activeClusterKeys = mutableSetOf<String>()

        fun showRider(location: InternetNode.RiderLocation, displayPosition: LatLng) {
            val id = location.riderId.toString()
            val self = id == mineId
            val age = (now - location.timestampMs).coerceAtLeast(0L)
            val quality = if (self) "You" else peerQuality[id] ?: location.connectionQuality
            val offline = !self && age >= MAP_OFFLINE_AFTER_MS
            val selected = selectedMapRiderId == id
            val statusColor = markerStatusColor(self, selected, quality, offline, age)
            val distance = if (self || mine == null) null else distanceMeters(mine, location)
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
                    MarkerOptions()
                        .position(displayPosition)
                        .icon(icon)
                        .anchor(0.5f, 1f)
                        .zIndex(if (self) 8f else if (selected) 7f else 4f)
                )!!.apply { tag = id }
            } else {
                marker.position = displayPosition
                marker.setIcon(icon)
                marker.tag = id
                marker.zIndex = if (self) 8f else if (selected) 7f else 4f
                marker.isVisible = true
            }
            shownRiderIds += id
        }

        // YOU is never swallowed by a cluster.
        mine?.let { showRider(it, LatLng(it.latitude, it.longitude)) }

        val remote = all.filter { it.riderId.toString() != mineId }
        val clusterRadiusPx = dp(MAP_CLUSTER_RADIUS_DP)
        val clusterRadiusSq = clusterRadiusPx * clusterRadiusPx
        val groups = mutableListOf<MutableList<InternetNode.RiderLocation>>()

        remote.forEach { location ->
            val point = projection.toScreenLocation(LatLng(location.latitude, location.longitude))
            val group = groups.firstOrNull { existing ->
                val first = existing.first()
                val firstPoint = projection.toScreenLocation(LatLng(first.latitude, first.longitude))
                val dx = point.x - firstPoint.x
                val dy = point.y - firstPoint.y
                dx * dx + dy * dy <= clusterRadiusSq
            }
            if (group == null) groups += mutableListOf(location) else group += location
        }

        val selfPoint = mine?.let { projection.toScreenLocation(LatLng(it.latitude, it.longitude)) }
        var expandedClusterStillExists = false

        groups.forEach { group ->
            val nearSelf = selfPoint != null && group.any { location ->
                val point = projection.toScreenLocation(LatLng(location.latitude, location.longitude))
                val dx = point.x - selfPoint.x
                val dy = point.y - selfPoint.y
                dx * dx + dy * dy <= clusterRadiusSq
            }
            val shouldCluster = group.size >= 2 || nearSelf
            if (!shouldCluster) {
                group.forEach { showRider(it, LatLng(it.latitude, it.longitude)) }
                return@forEach
            }

            val ids = group.map { it.riderId.toString() }.sorted()
            val idSet = ids.toSet()
            val clusterKey = ids.joinToString(",")
            val expanded = expandedClusterIds == idSet
            if (expanded) expandedClusterStillExists = true

            if (expanded) {
                val centerLat = group.map { it.latitude }.average()
                val centerLon = group.map { it.longitude }.average()
                val centerPoint = projection.toScreenLocation(LatLng(centerLat, centerLon))
                val hostWidth = liveMapHost?.width?.takeIf { it > 0 } ?: resources.displayMetrics.widthPixels
                val hostHeight = liveMapHost?.height?.takeIf { it > 0 } ?: resources.displayMetrics.heightPixels

                group.sortedBy { it.displayName.lowercase(Locale.ROOT) }.forEachIndexed { index, location ->
                    val column = (index % 3) - 1
                    val row = (index / 3) + 1
                    val desiredX = centerPoint.x + column * dp(118)
                    val desiredY = centerPoint.y - row * dp(66)
                    val x = desiredX.coerceIn(dp(70), (hostWidth - dp(70)).coerceAtLeast(dp(70)))
                    val y = desiredY.coerceIn(dp(54), (hostHeight - dp(40)).coerceAtLeast(dp(54)))
                    val displayPosition = projection.fromScreenLocation(android.graphics.Point(x, y))
                    showRider(location, displayPosition)
                }
            } else {
                // Hide the individual cards while collapsed.
                ids.forEach { riderMapMarkers[it]?.isVisible = false }

                val centerLat = group.map { it.latitude }.average()
                val centerLon = group.map { it.longitude }.average()
                var clusterPosition = LatLng(centerLat, centerLon)
                if (nearSelf && selfPoint != null) {
                    val shifted = android.graphics.Point(selfPoint.x, selfPoint.y - dp(62))
                    clusterPosition = projection.fromScreenLocation(shifted)
                }

                val clusterIcon = BitmapDescriptorFactory.fromBitmap(
                    createRiderClusterBitmap(group.size, nearSelf)
                )
                val existing = riderClusterMarkers[clusterKey]
                if (existing == null) {
                    riderClusterMarkers[clusterKey] = map.addMarker(
                        MarkerOptions()
                            .position(clusterPosition)
                            .icon(clusterIcon)
                            .anchor(0.5f, 1f)
                            .zIndex(if (nearSelf) 9f else 6f)
                    )!!.apply { tag = "cluster:$clusterKey" }
                } else {
                    existing.position = clusterPosition
                    existing.setIcon(clusterIcon)
                    existing.tag = "cluster:$clusterKey"
                    existing.zIndex = if (nearSelf) 9f else 6f
                    existing.isVisible = true
                }
                activeClusterKeys += clusterKey
            }
        }

        if (expandedClusterIds.isNotEmpty() && !expandedClusterStillExists) {
            expandedClusterIds = emptySet()
            mainHandler.removeCallbacks(clusterAutoCollapseRunnable)
        }

        riderMapMarkers.forEach { (id, marker) ->
            if (id !in shownRiderIds) marker.isVisible = false
        }
        riderClusterMarkers.keys.filter { it !in activeClusterKeys }.toList().forEach { key ->
            riderClusterMarkers.remove(key)?.remove()
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
        val width = dp(132)
        val height = dp(58)
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#E6070C0C") }
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = statusColor
            style = Paint.Style.STROKE
            strokeWidth = dp(if (stale) 1 else 2).toFloat()
        }
        val rect = RectF(dp(1).toFloat(), dp(1).toFloat(), (width - dp(1)).toFloat(), (height - dp(7)).toFloat())
        canvas.drawRoundRect(rect, dp(11).toFloat(), dp(11).toFloat(), bg)
        canvas.drawRoundRect(rect, dp(11).toFloat(), dp(11).toFloat(), stroke)
        canvas.drawCircle(dp(15).toFloat(), dp(17).toFloat(), dp(5).toFloat(),
            Paint(Paint.ANTI_ALIAS_FLAG).apply { color = statusColor })
        val arrow = Path().apply {
            moveTo(dp(15).toFloat(), dp(9).toFloat())
            lineTo(dp(11).toFloat(), dp(21).toFloat())
            lineTo(dp(15).toFloat(), dp(19).toFloat())
            lineTo(dp(19).toFloat(), dp(21).toFloat())
            close()
        }
        canvas.save()
        canvas.rotate(heading, dp(15).toFloat(), dp(17).toFloat())
        canvas.drawPath(arrow, Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.WHITE })
        canvas.restore()
        val title = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE; textSize = dp(11).toFloat()
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val info = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = if (stale) statusColor else Color.parseColor("#D7E1E0")
            textSize = dp(8).toFloat()
        }
        canvas.drawText(name.uppercase(Locale.ROOT).take(13), dp(27).toFloat(), dp(20).toFloat(), title)
        val d = when {
            distanceMeters == null -> "YOU"
            distanceMeters < 1000f -> "${distanceMeters.roundToInt()} m"
            distanceMeters < 10_000f -> String.format(Locale.US, "%.1f km", distanceMeters / 1000f)
            else -> "${(distanceMeters / 1000f).roundToInt()} km"
        }
        val detail = "${speedKmh.roundToInt()} km/h • $d" + if (stale) " • LAST" else ""
        canvas.drawText(detail.take(24), dp(11).toFloat(), dp(39).toFloat(), info)
        return bitmap
    }

    private fun createRiderClusterBitmap(count: Int, nearSelf: Boolean): Bitmap {
        val width = dp(72)
        val height = dp(58)
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val accent = Color.parseColor(if (nearSelf) "#00E5FF" else "#37D67A")
        val bg = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = Color.parseColor("#F0060B0B") }
        val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = accent
            style = Paint.Style.STROKE
            strokeWidth = dp(2).toFloat()
        }
        canvas.drawCircle(dp(36).toFloat(), dp(25).toFloat(), dp(22).toFloat(), bg)
        canvas.drawCircle(dp(36).toFloat(), dp(25).toFloat(), dp(22).toFloat(), stroke)
        canvas.drawLine(dp(36).toFloat(), dp(47).toFloat(), dp(36).toFloat(), dp(56).toFloat(), stroke)

        val number = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = dp(16).toFloat()
            textAlign = Paint.Align.CENTER
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = accent
            textSize = dp(7).toFloat()
            textAlign = Paint.Align.CENTER
            typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
        }
        canvas.drawText(count.toString(), dp(36).toFloat(), dp(27).toFloat(), number)
        canvas.drawText(if (nearSelf) "NEARBY" else "RIDERS", dp(36).toFloat(), dp(39).toFloat(), label)
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

    private fun dismissLiveRiderDetail() {
        mainHandler.removeCallbacks(riderDetailAutoHideRunnable)
        activeRiderDetailDialog?.dismiss()
        activeRiderDetailDialog = null
        activeRiderSheetExpanded = false
    }

    private fun scheduleRiderDetailAutoHide() {
        mainHandler.removeCallbacks(riderDetailAutoHideRunnable)
        mainHandler.postDelayed(riderDetailAutoHideRunnable, RIDER_DETAIL_AUTO_HIDE_MS)
    }

    private fun addRiderSheetStat(
        parent: LinearLayout,
        label: String,
        value: String,
        highlight: Boolean = false,
    ) {
        val cell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(8), dp(7), dp(8), dp(7))
        }
        cell.addView(TextView(this).apply {
            text = label.uppercase(Locale.ROOT)
            textSize = 8f
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
        })
        cell.addView(TextView(this).apply {
            text = value
            textSize = 13f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, if (highlight) R.color.accent else R.color.white))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(2)
        })
        parent.addView(cell, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
    }

    private fun showLiveRiderCard(location: InternetNode.RiderLocation) {
        dismissLiveRiderDetail()

        val mine = myLiveLocation
        val self = mine?.riderId == location.riderId
        val distance = if (self) null else mine?.let { distanceMeters(it, location) }
        val peer = internetNode.remotePeers().firstOrNull { it.id == location.riderId }
        val age = System.currentTimeMillis() - location.timestampMs
        val connection = if (self) {
            internetNode.currentConnectionQualityLabel()
        } else if (age >= MAP_OFFLINE_AFTER_MS) {
            "Last known"
        } else {
            peer?.qualityLabel ?: location.connectionQuality
        }

        val dialog = Dialog(this)
        activeRiderDetailDialog = dialog
        activeRiderSheetExpanded = false

        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(8), dp(16), dp(14))
            background = GradientDrawable().apply {
                cornerRadii = floatArrayOf(
                    dp(24).toFloat(), dp(24).toFloat(),
                    dp(24).toFloat(), dp(24).toFloat(),
                    0f, 0f, 0f, 0f,
                )
                setColor(Color.parseColor("#FA050909"))
                setStroke(dp(1), Color.parseColor("#30403E"))
            }
        }

        shell.addView(View(this).apply {
            background = GradientDrawable().apply {
                cornerRadius = dp(3).toFloat()
                setColor(Color.parseColor("#7C8A88"))
            }
        }, LinearLayout.LayoutParams(dp(48), dp(4)).apply {
            gravity = Gravity.CENTER_HORIZONTAL
            bottomMargin = dp(8)
        })

        val titleRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        titleRow.addView(TextView(this).apply {
            text = if (self) "${location.displayName.ifBlank { "YOU" }.uppercase(Locale.ROOT)}  •  YOU" else location.displayName.ifBlank { "RIDER" }.uppercase(Locale.ROOT)
            textSize = 19f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        titleRow.addView(MaterialButton(this).apply {
            text = "✕"
            textSize = 16f
            minWidth = 0
            minimumWidth = 0
            insetTop = 0
            insetBottom = 0
            cornerRadius = dp(20)
            backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.panel2))
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
            setOnClickListener { dismissLiveRiderDetail() }
        }, LinearLayout.LayoutParams(dp(42), dp(42)))
        shell.addView(titleRow)

        val previewStats = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            background = panelCardBackground(highlight = self)
        }
        addRiderSheetStat(previewStats, "Speed", "${location.speedKmh.roundToInt()} km/h", highlight = true)
        addRiderSheetStat(previewStats, "Distance", if (self) "YOU" else distance?.let(::formatMapDistance)?.replace(" from you", "") ?: "GPS…")
        shell.addView(previewStats, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(6)
        })

        val details = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = View.GONE
        }

        val detailStats = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
        }
        addRiderSheetStat(detailStats, "Connection", connection)
        addRiderSheetStat(detailStats, "Last update", if (self) "Now" else formatLastUpdate(location.timestampMs))
        details.addView(detailStats, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(4)
        })

        val phone = normalizeRiderPhone(location.phoneNumber)
        if (phone.isNotBlank()) {
            val phoneCard = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(12), dp(9), dp(12), dp(9))
                background = panelCardBackground()
            }
            phoneCard.addView(TextView(this).apply {
                text = "PHONE (OPTIONAL)"
                textSize = 8f
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
            })
            phoneCard.addView(TextView(this).apply {
                text = phone
                textSize = 14f
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
            })
            details.addView(phoneCard, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(6)
            })
        }

        if (!self) {
            val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            actions.addView(mapActionButton("NAVIGATE") {
                dismissLiveRiderDetail()
                openExternalNavigation(location)
            }, LinearLayout.LayoutParams(0, dp(50), 1f))
            actions.addView(mapActionButton("CALL") {
                dismissLiveRiderDetail()
                openRiderDialer(location.phoneNumber)
            }, LinearLayout.LayoutParams(0, dp(50), 1f).apply {
                marginStart = dp(5); marginEnd = dp(5)
            })
            actions.addView(mapActionButton("MESSAGE") {
                dismissLiveRiderDetail()
                openRiderMessage(location.phoneNumber)
            }, LinearLayout.LayoutParams(0, dp(50), 1f))
            details.addView(actions, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)).apply {
                topMargin = dp(7)
            })
        }

        val expandButton = MaterialButton(this).apply {
            text = "VIEW DETAILS  ▲"
            textSize = 10f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            cornerRadius = dp(12)
            strokeWidth = dp(1)
            strokeColor = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.border))
            backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.panel2))
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.accent))
        }

        fun setExpanded(expanded: Boolean) {
            activeRiderSheetExpanded = expanded
            details.visibility = if (expanded) View.VISIBLE else View.GONE
            expandButton.text = if (expanded) "HIDE DETAILS  ▼" else "VIEW DETAILS  ▲"
            scheduleRiderDetailAutoHide()
        }
        expandButton.setOnClickListener { setExpanded(!activeRiderSheetExpanded) }

        shell.addView(details)
        shell.addView(expandButton, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)).apply {
            topMargin = dp(7)
        })
        shell.addView(TextView(this).apply {
            text = "Tap outside or swipe down to close • Auto hides after 10 seconds"
            textSize = 8.5f
            gravity = Gravity.CENTER
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(5)
        })

        var downY = 0f
        shell.setOnTouchListener { _, event ->
            when (event.actionMasked) {
                android.view.MotionEvent.ACTION_DOWN -> {
                    downY = event.rawY
                    scheduleRiderDetailAutoHide()
                }
                android.view.MotionEvent.ACTION_UP -> {
                    val delta = event.rawY - downY
                    when {
                        delta > dp(72) && activeRiderSheetExpanded -> setExpanded(false)
                        delta > dp(72) -> dismissLiveRiderDetail()
                        delta < -dp(60) && !activeRiderSheetExpanded -> setExpanded(true)
                    }
                }
            }
            false
        }

        dialog.setContentView(shell)
        dialog.setCancelable(true)
        dialog.setCanceledOnTouchOutside(true)
        dialog.setOnDismissListener {
            mainHandler.removeCallbacks(riderDetailAutoHideRunnable)
            if (activeRiderDetailDialog === dialog) activeRiderDetailDialog = null
            activeRiderSheetExpanded = false
        }
        dialog.show()
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            clearFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            setGravity(Gravity.BOTTOM)
            setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
        }
        scheduleRiderDetailAutoHide()
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
                    setupMode = SetupMode.JOIN
                    binding.setupTitle.text = "JOIN RIDE"
                    binding.startRide.text = "JOIN RIDE"
                    binding.rideCode.setText(rideCode)
                    saveSettings()
                    stopLobbyDiscovery()
                    ensurePermissionsAndRun(PendingAction.START_RIDE)
                }
                .show()
        }
    }

    private fun panelCardBackground(highlight: Boolean = false): GradientDrawable =
        GradientDrawable().apply {
            cornerRadius = dp(16).toFloat()
            setColor(Color.parseColor(if (highlight) "#0B1716" else "#0A0F0F"))
            setStroke(
                dp(1),
                ContextCompat.getColor(this@MainActivity, if (highlight) R.color.accent else R.color.border)
            )
        }

    private fun showRideMeshPanel(
        title: String,
        subtitle: String? = null,
        buildContent: (LinearLayout, Dialog) -> Unit,
    ) {
        val dialog = Dialog(this)
        val accent = ContextCompat.getColor(this, R.color.accent)
        val white = ContextCompat.getColor(this, R.color.white)
        val muted = ContextCompat.getColor(this, R.color.muted)

        val shell = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(20), dp(20), dp(18))
            background = GradientDrawable().apply {
                cornerRadius = dp(26).toFloat()
                setColor(Color.parseColor("#050808"))
                setStroke(dp(1), Color.parseColor("#19302E"))
            }
        }

        shell.addView(TextView(this).apply {
            text = "RIDE MESH"
            textSize = 10f
            letterSpacing = 0.16f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(accent)
        })

        shell.addView(TextView(this).apply {
            text = title
            textSize = 27f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(white)
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(8)
        })

        if (!subtitle.isNullOrBlank()) {
            shell.addView(TextView(this).apply {
                text = subtitle
                textSize = 13f
                setTextColor(muted)
                setLineSpacing(0f, 1.16f)
            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
                topMargin = dp(5)
                bottomMargin = dp(14)
            })
        } else {
            shell.addView(View(this), LinearLayout.LayoutParams(1, dp(12)))
        }

        val body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        val scroll = ScrollView(this).apply {
            isFillViewport = false
            addView(body, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        shell.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))

        buildContent(body, dialog)

        addPanelButton(body, "CLOSE", primary = false) { dialog.dismiss() }

        dialog.setContentView(shell)
        dialog.setCancelable(true)
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            attributes = attributes.apply { dimAmount = 0.82f }
        }
        dialog.show()
        dialog.window?.setLayout(
            (resources.displayMetrics.widthPixels * 0.94f).toInt(),
            ViewGroup.LayoutParams.WRAP_CONTENT,
        )
    }

    private fun addPanelSection(parent: LinearLayout, label: String) {
        parent.addView(TextView(this).apply {
            text = label.uppercase(Locale.ROOT)
            textSize = 10f
            letterSpacing = 0.12f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(10)
            bottomMargin = dp(7)
        })
    }

    private fun addPanelInfo(parent: LinearLayout, label: String, value: String, highlight: Boolean = false) {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = panelCardBackground(highlight)
        }
        card.addView(TextView(this).apply {
            text = label.uppercase(Locale.ROOT)
            textSize = 9.5f
            letterSpacing = 0.08f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
        })
        card.addView(TextView(this).apply {
            text = value
            textSize = 15f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            setTextColor(ContextCompat.getColor(this@MainActivity, if (highlight) R.color.accent else R.color.white))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(4)
        })
        parent.addView(card, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            bottomMargin = dp(8)
        })
    }

    private fun addPanelButton(parent: LinearLayout, label: String, primary: Boolean = true, onClick: () -> Unit) {
        val accent = ContextCompat.getColor(this, R.color.accent)
        val panel = ContextCompat.getColor(this, R.color.panel2)
        val button = MaterialButton(this).apply {
            text = label
            textSize = 11.5f
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            cornerRadius = dp(14)
            strokeWidth = dp(1)
            strokeColor = ColorStateList.valueOf(if (primary) accent else ContextCompat.getColor(this@MainActivity, R.color.border))
            backgroundTintList = ColorStateList.valueOf(if (primary) accent else panel)
            setTextColor(if (primary) Color.BLACK else ContextCompat.getColor(this@MainActivity, R.color.white))
            setOnClickListener { onClick() }
        }
        parent.addView(button, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)).apply {
            topMargin = dp(6)
        })
    }

    private fun showRiderNameEditor() {
        showRideMeshPanel("RIDER NAME", "This is the name other riders see. Your email is never shown to the group.") { body, dialog ->
            val input = EditText(this).apply {
                setText(binding.riderName.text?.toString().orEmpty())
                hint = "Rider name"
                setSingleLine(true)
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
                setHintTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))
                backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.accent))
            }
            body.addView(input, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56)).apply {
                bottomMargin = dp(8)
            })
            addPanelButton(body, "SAVE RIDER NAME") {
                val name = input.text?.toString().orEmpty().trim().take(24)
                if (name.isBlank()) {
                    input.error = "Enter a rider name"
                } else {
                    binding.riderName.setText(name)
                    prefs.edit().putString("rider", name).apply()
                    dialog.dismiss()
                }
            }
        }
    }

    private fun showRiderPhoneEditor() {
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

    private fun showRidersDialog() {
        if (ridersScreen == null) {
            val screen = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setBackgroundColor(Color.parseColor("#020809"))
                setPadding(dp(16), dp(12), dp(16), dp(4))
            }
            val header = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
            header.addView(MaterialButton(this).apply {
                text = "‹"; textSize = 28f; contentDescription = "Back to ride"
                setTextColor(Color.WHITE); backgroundTintList = ColorStateList.valueOf(Color.TRANSPARENT)
                minWidth = 0; setPadding(0, 0, 0, 0)
                setOnClickListener { showScreen(Screen.ACTIVE) }
            }, LinearLayout.LayoutParams(dp(48), dp(56)))
            header.addView(TextView(this).apply {
                text = "RIDERS\n8 RIDERS MAX"; textSize = 18f
                setTextColor(Color.WHITE); setTypeface(Typeface.DEFAULT, Typeface.BOLD)
            }, LinearLayout.LayoutParams(0, dp(56), 1f))
            header.addView(MaterialButton(this).apply {
                text = "+"; textSize = 26f; contentDescription = "Invite riders"
                minWidth = 0; setPadding(0, 0, 0, 0); cornerRadius = dp(24)
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.accent))
                backgroundTintList = ColorStateList.valueOf(Color.parseColor("#05242A"))
                setOnClickListener { showLiveInviteOptions() }
            }, LinearLayout.LayoutParams(dp(48), dp(56)))
            screen.addView(header)
            ridersList = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            val scroll = android.widget.ScrollView(this).apply { addView(ridersList) }
            screen.addView(scroll, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(16) })
            screen.addView(MaterialButton(this).apply {
                text = "+  INVITE RIDERS"; textSize = 12f; cornerRadius = dp(14)
                strokeWidth = dp(1); strokeColor = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.accent))
                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.accent))
                backgroundTintList = ColorStateList.valueOf(Color.TRANSPARENT)
                setOnClickListener { showLiveInviteOptions() }
            }, LinearLayout.LayoutParams(-1, dp(60)))
            screen.addView(TextView(this).apply {
                text = "8 RIDERS MAX PER GROUP"; textSize = 9f; gravity = Gravity.CENTER
                letterSpacing = 0.1f; setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
            }, LinearLayout.LayoutParams(-1, dp(32)))
            screen.addView(buildRideMainNav(Screen.RIDERS), LinearLayout.LayoutParams(-1, dp(74)))
            (binding.root as ViewGroup).addView(screen, FrameLayout.LayoutParams(-1, -1))
            ridersScreen = screen
        }
        renderRiderGrid()
        showScreen(Screen.RIDERS)
    }

    private fun renderRidersScreen() {
        val list = ridersList ?: return
        list.removeAllViews()
        currentRiders.forEach { rider ->
            val row = buildRiderTile(rider) as LinearLayout
            row.background = null
            val menu = MaterialButton(this).apply {
                text = "⋮"; textSize = 22f; minWidth = 0; setPadding(0, 0, 0, 0)
                contentDescription = "Details for ${rider.name}"
                setTextColor(Color.WHITE); backgroundTintList = ColorStateList.valueOf(Color.TRANSPARENT)
                setOnClickListener {
                    showRideMeshPanel(rider.name, if (rider.self) "YOUR RIDER PROFILE" else "RIDER DETAILS") { body, _ ->
                        addPanelInfo(body, "Device", rider.device.ifBlank { "Unknown device" })
                        addPanelInfo(body, "Connection", rider.path)
                        addPanelInfo(body, "Signal", "${rider.qualityBars} of 4")
                    }
                }
            }
            row.addView(menu, LinearLayout.LayoutParams(dp(48), dp(48)))
            list.addView(row, LinearLayout.LayoutParams(-1, dp(76)))
            list.addView(View(this).apply { setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.border)) }, LinearLayout.LayoutParams(-1, dp(1)))
        }
        if (currentRiders.size <= 1) list.addView(TextView(this).apply {
            text = "Invite your group. Riders appear here when they connect."
            textSize = 13f; setPadding(dp(12), dp(28), dp(12), dp(28))
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
        })
    }

    private fun showAudioRouteDialog() {
        val current = when (binding.audioRoute.checkedRadioButtonId) {
            R.id.routePhone -> "Phone"
            R.id.routeHelmet -> "Helmet / headset"
            else -> "Automatic"
        }
        showRideMeshPanel("AUDIO", "Choose where RideMesh voice should play. Automatic is recommended while riding.") { body, dialog ->
            addPanelInfo(body, "Current route", current, highlight = true)
            addPanelInfo(body, "Voice", if (micMuted) "Microphone muted • listening only" else "Microphone active")

            addPanelSection(body, "Audio route")
            addPanelButton(body, if (current == "Automatic") "✓  AUTOMATIC" else "AUTOMATIC") {
                binding.routeAuto.isChecked = true
                applySelectedAudioRoute()
                saveSettings()
                dialog.dismiss()
            }
            addPanelButton(body, if (current == "Phone") "✓  PHONE" else "PHONE", primary = false) {
                binding.routePhone.isChecked = true
                applySelectedAudioRoute()
                saveSettings()
                dialog.dismiss()
            }
            addPanelButton(body, if (current == "Helmet / headset") "✓  HELMET / HEADSET" else "HELMET / HEADSET", primary = false) {
                binding.routeHelmet.isChecked = true
                applySelectedAudioRoute()
                saveSettings()
                dialog.dismiss()
            }
        }
    }

    private fun transportModeLabel(): String =
        if (transportMode == TransportMode.LOCAL_ONLY) "OFFLINE MESH • OPUS" else "INTERNET VOICE"

    private fun showTransportModeDialog() {
        if (rideStarted) {
            AlertDialog.Builder(this).setMessage("End the ride before changing connection mode.")
                .setPositiveButton("OK", null).show()
            return
        }
        AlertDialog.Builder(this).setTitle("Voice connection")
            .setSingleChoiceItems(arrayOf("Offline mesh — six-rider test", "Internet voice"),
                if (transportMode == TransportMode.LOCAL_ONLY) 0 else 1) { dialog, which ->
                transportMode = if (which == 0) TransportMode.LOCAL_ONLY else TransportMode.INTERNET_ONLY
                saveSettings()
                applySelectedAudioRoute()
                dialog.dismiss()
            }.setNegativeButton("CANCEL", null).show()
    }

    private fun showMeshLabRoleDialog() {
        val roles = MeshNode.LabRole.values()
        val choices = arrayOf("NORMAL — automatic nearby links", "A — B only", "B — A and C",
            "C — B and D", "D — C and E", "E — D and F", "F — E only")
        AlertDialog.Builder(this).setTitle("Six-phone relay test role")
            .setSingleChoiceItems(choices, roles.indexOf(meshLabRole)) { dialog, which ->
                meshLabRole = roles[which]
                saveSettings()
                if (rideStarted && transportMode == TransportMode.LOCAL_ONLY) {
                    restartLocalMeshForRoleOrMode("test role ${meshLabRole.name}")
                }
                dialog.dismiss()
            }.setNegativeButton("CANCEL", null).show()
    }

    private fun ensurePremiumAccess(): Boolean {
        premiumEntryAction = PremiumEntryAction.NONE
        return true // Billing-free testing package requested by owner.
    }

    private fun showPremiumPaywall() {
        Toast.makeText(this, "Testing build — no subscription required", Toast.LENGTH_SHORT).show()
    }

    private fun renderPremiumPage() {
        binding.screenPremium.visibility = View.GONE
    }

    private fun continueAfterPremiumUnlock() {
        val action = premiumEntryAction
        if (action == PremiumEntryAction.NONE) return
        premiumEntryAction = PremiumEntryAction.NONE
        when (action) {
            PremiumEntryAction.CREATE_RIDE -> {
                binding.setupTitle.text = "CREATE RIDE"
                binding.rideCode.setText(generateRideCode())
                showScreen(Screen.SETUP)
            }
            PremiumEntryAction.JOIN_RIDE -> {
                binding.setupTitle.text = "JOIN RIDE"
                showScreen(Screen.SETUP)
                binding.rideCode.requestFocus()
            }
            PremiumEntryAction.START_RIDE -> {
                showScreen(Screen.SETUP)
                ensurePermissionsAndRun(PendingAction.START_RIDE)
            }
            PremiumEntryAction.NONE -> Unit
        }
    }

    private fun showSettingsAndHelpDialog() {
        val email = savedUserEmail().ifBlank { "Not set" }
        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { riderNameFromEmail(email) }
        showRideMeshPanel("SETTINGS", "RideMesh profile, support and ride preferences.") { body, dialog ->
            addPanelSection(body, "Rider profile")
            addPanelInfo(body, "Rider name", rider, highlight = true)
            addPanelInfo(body, "Email", email)
            val phone = prefs.getString(RIDER_PHONE_KEY, "").orEmpty().ifBlank { "Not set" }
            addPanelInfo(body, "Phone", phone)
            addPanelSection(body, "App")
            addPanelInfo(body, "Version", appVersionLabel(), highlight = true)
            addPanelInfo(body, "Connection", transportModeLabel())
            addPanelButton(body, "VOICE CONNECTION", primary = false) {
                dialog.dismiss()
                showTransportModeDialog()
            }
            addPanelButton(body, "OFFLINE TEST ROLE: ${meshLabRole.name}", primary = false) {
                dialog.dismiss()
                showMeshLabRoleDialog()
            }
            addPanelButton(body, "OFFLINE DIAGNOSTICS", primary = false) {
                dialog.dismiss()
                showOfflineDiagnosticsDialog()
            }
            addPanelButton(body, "EDIT RIDER NAME") {
                dialog.dismiss()
                showRiderNameEditor()
            }
            addPanelButton(body, "EDIT PHONE NUMBER", primary = false) {
                dialog.dismiss()
                showRiderPhoneEditor()
            }
            addPanelButton(body, "CHANGE EMAIL", primary = false) {
                dialog.dismiss()
                showEmailProfileScreen()
            }

            addPanelSection(body, "Support")
            addPanelButton(body, "EMAIL SUPPORT") {
                dialog.dismiss()
                openEmailSupport()
            }
            if (rideStarted) {
                addPanelButton(body, "RIDE STATUS", primary = false) {
                    dialog.dismiss()
                    showRideStatusDialog()
                }
            }
        }
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

    private fun betaStatusSentence(): String = "Access: active"

    private fun appVersionLabel(): String {
        val info = packageManager.getPackageInfo(packageName, 0)
        val versionCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            info.longVersionCode
        } else {
            @Suppress("DEPRECATION")
            info.versionCode.toLong()
        }
        return "RideMesh ${info.versionName ?: "1.0.1"} • Build $versionCode"
    }

    private fun refreshBetaAccessUi(showWarning: Boolean) {
        binding.betaExpiryStatus.visibility = View.VISIBLE
        binding.betaExpiryStatus.text = appVersionLabel()
    }

    private fun ensureBetaUsable(): Boolean = true

    private fun maybeShowBetaWarning(days: Long) = Unit

    private fun showBetaExpiredDialog() = Unit

    private fun expireActiveRide() = Unit

    private fun showOfflineDiagnosticsDialog() {
        val d = meshNode.diagnostics()
        AlertDialog.Builder(this).setTitle("Offline mesh • build 32")
            .setMessage("Role: ${meshLabRole}\nDirect links: ${d.directPeers}\nReceived: ${d.receivedPackets}\nRelayed: ${d.relayedPackets}\nMaximum hops: ${d.maxObservedHops}\nAdvertising: ${d.advertisingActive}\nDiscovery: ${d.discoveryActive}\nSend failures: ${d.sendFailures}\nLast error: ${d.lastError}\n\nOpus 16 kHz / 20 ms / 32 kbps target.\nReachable riders: ${d.reachableRiders}\nAudio drops: ${d.droppedAudio}")
            .setPositiveButton("OK", null).show()
    }

    private fun showRideStatusDialog() {
        if (transportMode == TransportMode.LOCAL_ONLY) { showOfflineDiagnosticsDialog(); return }
        val diag = internetNode.diagnostics()
        val connection = when {
            diag.voicePeersConnected > 0 -> "Connected"
            diag.signalingConnected -> "Ready"
            else -> "Reconnecting…"
        }
        val voice = when {
            micMuted -> "Muted"
            diag.voicePeersConnected > 0 -> "Connected"
            else -> "Ready"
        }
        val quality = when {
            diag.voicePeersConnected > 0 -> "Good"
            diag.signalingConnected -> "Ready"
            else -> "Checking"
        }
        val riders = (diag.knownRiders + 1).coerceAtLeast(1)

        showRideMeshPanel("RIDE STATUS", "Live rider-facing connection information.") { body, dialog ->
            addPanelInfo(body, "Connection", connection, highlight = connection == "Connected")
            addPanelInfo(body, "Voice", voice)
            addPanelInfo(body, "Riders", "$riders connected")
            addPanelInfo(body, "Microphone", if (micMuted) "Muted • listening only" else "Active")
            addPanelInfo(body, "Voice quality", quality)
            addPanelButton(body, "EMAIL SUPPORT") {
                dialog.dismiss()
                openEmailSupport()
            }
        }
    }

    private fun openEmailSupport() {
        val diag = internetNode.diagnostics()
        val rideCode = normalizedRideCode().ifBlank { "Not active" }
        val connection = when {
            diag.voicePeersConnected > 0 -> "Connected"
            diag.signalingConnected -> "Ready"
            else -> "Reconnecting"
        }
        val voice = when {
            micMuted -> "Muted"
            diag.voicePeersConnected > 0 -> "Connected"
            else -> "Ready"
        }
        val appVersion = runCatching {
            packageManager.getPackageInfo(packageName, 0).versionName ?: "Unknown"
        }.getOrDefault("Unknown")
        val subject = "RideMesh Support"
        val body = buildString {
            appendLine("Please describe your issue below:")
            appendLine()
            appendLine("--------------------------------")
            appendLine("RideMesh diagnostic information")
            appendLine("App version: $appVersion")
            appendLine("Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
            appendLine("Device: ${Build.MANUFACTURER} ${Build.MODEL}")
            appendLine("Ride code: $rideCode")
            appendLine("Connection: $connection")
            appendLine("Voice: $voice")
            appendLine("Visible riders: ${(diag.knownRiders + 1).coerceAtLeast(1)}")
            appendLine("--------------------------------")
        }
        val mailUri = Uri.parse(
            "mailto:$SUPPORT_EMAIL?subject=${Uri.encode(subject)}&body=${Uri.encode(body)}"
        )
        val intent = Intent(Intent.ACTION_SENDTO, mailUri)
        runCatching {
            startActivity(Intent.createChooser(intent, "Email RideMesh Support"))
        }.onFailure {
            Toast.makeText(this, "No email app found", Toast.LENGTH_LONG).show()
        }
    }

    private fun openRideMeshCommunity() {
        openEmailSupport()
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
        // Public build intentionally suppresses verbose transport / infrastructure diagnostics.
    }

    override fun onResume() {
        super.onResume()
        appInForeground = true
    }

    override fun onPause() {
        appInForeground = false
        super.onPause()
    }

    override fun onDestroy() {
        if (::billingManager.isInitialized) billingManager.endConnection()
        saveSettings()
        mainHandler.removeCallbacks(stopLobbyScan)
        mainHandler.removeCallbacks(rideWatchdog)
        if (::lobbyNode.isInitialized) lobbyNode.stop()
        if (::internetNode.isInitialized && !rideStarted) internetNode.stop()
        if (!rideStarted && ::audioEngine.isInitialized) audioEngine.release()
        super.onDestroy()
    }

    companion object {
        private const val RIDER_PHONE_KEY = "rider_phone"
        private const val LIVE_MAP_FRAGMENT_TAG = "ridemesh_live_rider_map"
        private const val LOCATION_GPS_INTERVAL_MS = 1_000L
        private const val LOCATION_GPS_MIN_INTERVAL_MS = 750L
        private const val LOCATION_GPS_MAX_DELAY_MS = 1_500L
        private const val MAP_WEAK_AFTER_MS = 6_000L
        private const val MAP_OFFLINE_AFTER_MS = 15_000L
        private const val MAP_AUTO_FIT_COOLDOWN_MS = 5_000L
        private const val MAP_CLUSTER_RADIUS_DP = 88
        private const val MAP_CLUSTER_EXPAND_TIMEOUT_MS = 10_000L
        private const val RIDER_DETAIL_AUTO_HIDE_MS = 10_000L
        private const val MAP_RENDER_MIN_INTERVAL_MS = 500L
        private const val LOCATION_STATIONARY_HEARTBEAT_MS = 5_000L
        private const val LOCATION_SHARE_HEARTBEAT_CHECK_MS = 1_000L
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
        private const val SELF_TILE_KEY = "self"
        private const val MAX_VISIBLE_RIDER_TILES = 8
        private const val SPEAKING_HOLD_MS = 560L
        private const val LOBBY_SCAN_WINDOW_MS = 20_000L
        private const val WATCHDOG_INTERVAL_MS = 5_000L
        private const val INTERNET_STABLE_BEFORE_MESH_SLEEP_MS = 15_000L
        private const val LOCAL_MESH_REFRESH_MS = 8_000L
        private const val LOCAL_MESH_RESTART_SETTLE_MS = 700L
        private const val BETA_FIRST_LAUNCH_KEY = "beta_first_launch_ms_v2"
        private const val BETA_WARNING_BUCKET_KEY = "beta_warning_bucket_v2"
        private const val USER_EMAIL_KEY = "user_email_v1"
        private const val SUPPORT_EMAIL = "salesautopilotindia@gmail.com"
    }
}
