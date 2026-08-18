from pathlib import Path


def replace_section(text: str, start: str, end: str, replacement: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + replacement + text[j:]


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing patch anchor: {old[:120]!r}")
    return text.replace(old, new, 1)

# Version
p = Path("app/build.gradle.kts")
s = p.read_text()
s = replace_once(s, 'versionCode = 16\n        versionName = "0.4.6-beta1.2"', 'versionCode = 17\n        versionName = "0.4.7-beta1.3"')
p.write_text(s)

# Audio: expose a clean stream switch so old group audio cannot spill into the new group.
p = Path("app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt")
s = p.read_text()
s = replace_once(
    s,
    '    private fun clearRemoteAudio() {\n        sourceQueues.values.forEach { queue -> synchronized(queue) { queue.clear() } }\n        sourcePrimed.clear()\n        sourceLastSeenMs.clear()\n    }',
    '    private fun clearRemoteAudio() {\n        sourceQueues.values.forEach { queue -> synchronized(queue) { queue.clear() } }\n        sourcePrimed.clear()\n        sourceLastSeenMs.clear()\n    }\n\n    /** Clears received voice when switching between primary and secondary groups. */\n    fun resetIncomingAudio() {\n        clearRemoteAudio()\n        playbackActiveUntilMs = 0L\n        audioTrack?.let {\n            try { it.pause() } catch (_: Throwable) {}\n            try { it.flush() } catch (_: Throwable) {}\n            try { if (!focusPaused.get()) it.play() } catch (_: Throwable) {}\n        }\n    }'
)
p.write_text(s)

# Main activity dual group logic.
p = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = p.read_text()
s = replace_once(s, 'import android.widget.GridLayout\n', 'import android.widget.EditText\nimport android.widget.GridLayout\n')
s = replace_once(
    s,
    '    private lateinit var internetNode: InternetNode\n    private lateinit var audioEngine: AudioEngine',
    '    private lateinit var internetNode: InternetNode\n    private lateinit var secondaryInternetNode: InternetNode\n    private lateinit var audioEngine: AudioEngine'
)
s = replace_once(
    s,
    '    private var lastMeshRefreshMs = 0L\n\n    private enum class PendingAction',
    '    private var lastMeshRefreshMs = 0L\n    private var primaryRideCode = ""\n    private var secondaryRideCode: String? = null\n    private var secondaryPeerCount = 0\n    private var secondaryHadConnection = false\n    private var activeGroup = ActiveGroup.PRIMARY\n\n    private enum class ActiveGroup { PRIMARY, SECONDARY }\n    private enum class PendingAction'
)
s = replace_once(
    s,
    '        internetNode = InternetNode(this)\n        audioEngine = AudioEngine(',
    '''        internetNode = InternetNode(this)
        secondaryInternetNode = InternetNode(object : InternetNode.Listener {
            override fun onInternetState(connected: Boolean, message: String) {
                runOnUiThread {
                    log("Secondary • $message")
                    if (connected) secondaryHadConnection = true
                    if (!connected && secondaryHadConnection && activeGroup == ActiveGroup.SECONDARY && primaryPathAvailable()) {
                        switchActiveGroup(ActiveGroup.PRIMARY, "Secondary link lost • returned to primary")
                    } else {
                        updateTransportStatus()
                        updateCapturePolicy()
                    }
                }
            }

            override fun onInternetPeerCount(count: Int) {
                secondaryPeerCount = count
                runOnUiThread { if (activeGroup == ActiveGroup.SECONDARY) updateTransportStatus() }
            }

            override fun onInternetAudio(sourceId: String, audio: ByteArray) {
                if (!rideStarted || activeGroup != ActiveGroup.SECONDARY) return
                markRiderSpeaking(sourceId)
                audioEngine.playIncoming("secondary:$sourceId", audio)
            }
        })
        audioEngine = AudioEngine('''
)
s = replace_once(
    s,
    '        binding.activeStatus.setOnClickListener { showRideStatusDialog() }',
    '        binding.activeStatus.setOnClickListener { showRideStatusDialog() }\n        binding.groupSwitcher.setOnClickListener { showGroupsDialog() }'
)

# Invite current active group and expose group management.
s = replace_section(
    s,
    '    private fun showLiveInviteOptions() {',
    '    private fun buildRideQrBitmap',
    '''    private fun showLiveInviteOptions() {
        val secondaryActive = activeGroup == ActiveGroup.SECONDARY
        val options = if (secondaryActive) {
            arrayOf("Show QR code", "Share QR code", "Manage primary / secondary groups")
        } else {
            arrayOf("Show QR code", "Share QR code", "Find nearby RideMesh riders", "Manage primary / secondary groups")
        }
        AlertDialog.Builder(this)
            .setTitle("Invite to ${currentInviteCode()}")
            .setItems(options) { _, which ->
                if (secondaryActive) {
                    when (which) {
                        0 -> showRideQr()
                        1 -> shareRideQr()
                        2 -> showGroupsDialog()
                    }
                } else {
                    when (which) {
                        0 -> showRideQr()
                        1 -> shareRideQr()
                        2 -> ensurePermissionsAndRun(PendingAction.FIND_RIDERS)
                        3 -> showGroupsDialog()
                    }
                }
            }
            .setNegativeButton("CLOSE", null)
            .show()
    }

'''
)
s = replace_once(
    s,
    '        val code = normalizedRideCode()\n        binding.rideCode.setText(code)\n        saveSettings()',
    '        val code = currentInviteCode()\n        if (!rideStarted || activeGroup == ActiveGroup.PRIMARY) {\n            binding.rideCode.setText(code)\n            saveSettings()\n        }'
)
s = replace_once(s, '        val code = normalizedRideCode()\n        try {', '        val code = currentInviteCode()\n        try {')

# Primary ride start and audio routing.
s = replace_section(
    s,
    '    private fun startRideNow() {',
    '    private fun sendHybridAudio',
    '''    private fun startRideNow() {
        if (rideStarted) return

        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val code = normalizedRideCode()
        binding.riderName.setText(rider)
        binding.rideCode.setText(code)
        saveSettings()

        try {
            stopLobbyDiscovery()
            startRideServiceSafely()

            rideStarted = true
            primaryRideCode = code
            secondaryRideCode = null
            secondaryPeerCount = 0
            secondaryHadConnection = false
            activeGroup = ActiveGroup.PRIMARY
            secondaryInternetNode.stop()
            directPeerCount = 0
            internetPeerCount = 0
            meshRunning = false
            internetConnectedSinceMs = 0L
            lastMeshRefreshMs = 0L

            applySelectedAudioRoute()
            audioEngine.selectCommunicationDevice()

            ensureLocalMeshRunning("initial fallback")
            internetNode.start(primaryRideCode, rider, deviceLabel())

            showScreen(Screen.ACTIVE)
            updateTransportStatus()
            updateCapturePolicy()

            mainHandler.removeCallbacks(rideWatchdog)
            mainHandler.postDelayed(rideWatchdog, WATCHDOG_INTERVAL_MS)
            log("Primary ride started • dual-group ready • automatic Internet / local reconnect enabled")
        } catch (t: Throwable) {
            recoverFromStartFailure(t)
        }
    }

'''
)
s = replace_section(
    s,
    '    private fun sendHybridAudio(audio: ByteArray) {',
    '    private fun ensureLocalMeshRunning',
    '''    private fun sendHybridAudio(audio: ByteArray) {
        if (!rideStarted || audio.isEmpty()) return

        if (activeGroup == ActiveGroup.SECONDARY) {
            if (secondaryInternetNode.isConnected()) {
                secondaryInternetNode.sendLocalAudio(audio)
            }
            return
        }

        if (internetNode.isConnected()) {
            if (!internetNode.sendLocalAudio(audio)) {
                ensureLocalMeshRunning("Internet send failed")
                meshNode.sendLocalAudio(audio)
            }
        } else {
            ensureLocalMeshRunning("local voice path")
            meshNode.sendLocalAudio(audio)
        }
    }

'''
)
s = replace_once(s, '            normalizedRideCode(),\n            MeshNode.LabRole.NORMAL,', '            primaryRideCode.ifBlank { normalizedRideCode() },\n            MeshNode.LabRole.NORMAL,')
s = replace_section(
    s,
    '    private fun updateCapturePolicy() {',
    '    private fun startRideServiceSafely',
    '''    private fun updateCapturePolicy() {
        if (!rideStarted) return

        if (activeGroup == ActiveGroup.SECONDARY) {
            if (secondaryInternetNode.isConnected()) {
                audioEngine.startTransmit()
            } else {
                audioEngine.stopTransmit()
                updateAudioUi("Secondary reconnecting • microphone sleeping")
            }
            return
        }

        if (internetNode.isConnected() || directPeerCount > 0) {
            audioEngine.startTransmit()
        } else {
            audioEngine.stopTransmit()
            updateAudioUi("Reconnecting • microphone sleeping")
        }
    }

'''
)
# Stop / cleanup both groups.
s = replace_once(s, '        internetNode.stop()\n        meshRunning = false', '        internetNode.stop()\n        secondaryInternetNode.stop()\n        meshRunning = false')
s = replace_once(
    s,
    '        internetConnectedSinceMs = 0L\n        binding.riderCount.text = "RIDE ACTIVE"',
    '        internetConnectedSinceMs = 0L\n        primaryRideCode = ""\n        secondaryRideCode = null\n        secondaryPeerCount = 0\n        secondaryHadConnection = false\n        activeGroup = ActiveGroup.PRIMARY\n        binding.riderCount.text = "RIDE ACTIVE"'
)

# Primary callbacks only feed audio while primary is the foreground group; active status is group-aware.
s = replace_section(
    s,
    '    override fun onAudioPacket(sourceId: String, audio: ByteArray) {',
    '    private fun markRiderSpeaking',
    '''    override fun onAudioPacket(sourceId: String, audio: ByteArray) {
        if (!rideStarted || activeGroup != ActiveGroup.PRIMARY) return
        val tileKey = meshNode.endpointIdForSource(sourceId) ?: sourceId
        markRiderSpeaking(tileKey)
        audioEngine.playIncoming(sourceId, audio)
    }

    override fun onInternetState(connected: Boolean, message: String) {
        runOnUiThread {
            log(message)
            if (connected) {
                if (internetConnectedSinceMs == 0L) internetConnectedSinceMs = System.currentTimeMillis()
            } else {
                internetConnectedSinceMs = 0L
                stopLobbyDiscovery()
                if (rideStarted) ensureLocalMeshRunning("Internet path lost")
            }
            updateTransportStatus()
            updateCapturePolicy()
        }
    }

    override fun onInternetPeerCount(count: Int) {
        internetPeerCount = count
        runOnUiThread { updateTransportStatus() }
    }

    override fun onInternetAudio(sourceId: String, audio: ByteArray) {
        if (!rideStarted || activeGroup != ActiveGroup.PRIMARY) return
        markRiderSpeaking(sourceId)
        audioEngine.playIncoming(sourceId, audio)
    }

    private fun updateTransportStatus() {
        if (!rideStarted) return

        if (activeGroup == ActiveGroup.SECONDARY) {
            val connected = secondaryInternetNode.isConnected()
            val total = secondaryPeerCount + 1
            binding.networkTile.text = if (connected) "INTERNET" else "SEARCHING"
            binding.riderCount.text = if (connected && secondaryPeerCount > 0) "$total RIDERS CONNECTED" else if (connected) "SECOND GROUP ACTIVE" else "SECOND GROUP RECONNECTING…"
            binding.meshStatus.text = if (connected) "SECONDARY INTERNET VOICE • PRIMARY STAYS CONNECTED" else "SECONDARY RECONNECTING • PRIMARY AVAILABLE"
            binding.activeGroupLabel.text = "SECONDARY"
            binding.activeRideCode.text = secondaryRideCode ?: "—"
            binding.activeRiders.text = "RIDERS ${if (connected) total else 1}"
        } else {
            when {
                internetNode.isConnected() -> {
                    val total = internetPeerCount + 1
                    binding.networkTile.text = "INTERNET"
                    binding.riderCount.text = if (internetPeerCount > 0) "$total RIDERS CONNECTED" else "RIDE ACTIVE"
                    binding.meshStatus.text = if (binding.batterySaver.isChecked && !meshRunning) {
                        "INTERNET VOICE • AUTO LOCAL FALLBACK"
                    } else {
                        "INTERNET VOICE • LOCAL MESH WARM"
                    }
                }
                directPeerCount > 0 -> {
                    val total = directPeerCount + 1
                    binding.networkTile.text = "LOCAL MESH"
                    binding.riderCount.text = "$total RIDERS NEARBY"
                    binding.meshStatus.text = "LOCAL VOICE • AUTO RECONNECT ACTIVE"
                }
                else -> {
                    binding.networkTile.text = "SEARCHING"
                    binding.riderCount.text = "RECONNECTING…"
                    binding.meshStatus.text = "AUTO RECONNECT • INTERNET + NEARBY SEARCH"
                }
            }
            binding.activeGroupLabel.text = "PRIMARY"
            binding.activeRideCode.text = primaryRideCode.ifBlank { normalizedRideCode() }
            val visibleRiderTotal = when {
                internetNode.isConnected() -> internetPeerCount + 1
                directPeerCount > 0 -> directPeerCount + 1
                else -> 1
            }
            binding.activeRiders.text = "RIDERS $visibleRiderTotal"
        }

        binding.homeNetworkStatus.text = when {
            internetNode.isConnected() -> "●  INTERNET VOICE ACTIVE"
            directPeerCount > 0 -> "●  LOCAL MESH ACTIVE"
            else -> "●  READY TO RIDE"
        }
        renderRiderGrid()
        applyPowerUi()
    }

'''
)

s = replace_section(
    s,
    '    private fun renderRiderGrid() {',
    '    private fun buildRiderTile',
    '''    private fun renderRiderGrid() {
        if (!rideStarted || !::binding.isInitialized) return

        val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val meDevice = deviceLabel()
        val secondary = activeGroup == ActiveGroup.SECONDARY
        val primaryConnected = internetNode.isConnected() || directPeerCount > 0
        val activeConnected = if (secondary) secondaryInternetNode.isConnected() else primaryConnected
        val riders = mutableListOf(
            RiderTile(
                key = SELF_TILE_KEY,
                name = me,
                device = meDevice,
                qualityBars = if (activeConnected) 4 else 1,
                path = if (secondary) "Secondary Internet" else if (internetNode.isConnected()) "Internet" else if (directPeerCount > 0) "Local" else "Searching",
                self = true,
            )
        )

        if (secondary) {
            if (secondaryInternetNode.isConnected()) {
                secondaryInternetNode.remotePeers().forEach { peer ->
                    riders += RiderTile(
                        key = peer.id.toString(),
                        name = peer.displayName,
                        device = peer.deviceName,
                        qualityBars = peer.qualityBars,
                        path = "Secondary Internet",
                    )
                }
            }
        } else if (internetNode.isConnected()) {
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
                height = dp(118)
                setMargins(dp(4), dp(4), dp(4), dp(4))
            })
        }
    }

'''
)
# Bigger avatar/name tiles to match approved mockup.
s = replace_once(s, '        card.addView(avatar, LinearLayout.LayoutParams(dp(52), dp(52)))', '        card.addView(avatar, LinearLayout.LayoutParams(dp(64), dp(64)))')
s = replace_once(s, '            textSize = 22f', '            textSize = 27f')
s = replace_once(s, '            textSize = 10.5f', '            textSize = 12f')
s = replace_once(s, '            textSize = 9.5f', '            textSize = 10.5f')

# Incoming Nearby invite can now become the temporary secondary group instead of forcing an end.
s = replace_section(
    s,
    '    override fun onRideInviteReceived(inviterName: String, rideCode: String) {',
    '    private fun showRidersDialog',
    '''    override fun onRideInviteReceived(inviterName: String, rideCode: String) {
        runOnUiThread {
            if (rideStarted) {
                val samePrimary = primaryRideCode.equals(rideCode, true)
                val sameSecondary = secondaryRideCode?.equals(rideCode, true) == true
                if (samePrimary || sameSecondary) {
                    AlertDialog.Builder(this)
                        .setTitle("Already connected")
                        .setMessage("$inviterName invited you to a RideMesh group already on this phone.")
                        .setPositiveButton("OK", null)
                        .show()
                } else {
                    AlertDialog.Builder(this)
                        .setTitle("Join as second group?")
                        .setMessage("$inviterName invited you to $rideCode. Your primary group $primaryRideCode will stay connected in the background. Secondary voice uses Internet in this Beta.")
                        .setNegativeButton("DECLINE", null)
                        .setPositiveButton("JOIN SECOND GROUP") { _, _ -> startSecondaryGroup(rideCode) }
                        .show()
                }
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

'''
)

# Active rider details are for whichever group is foreground.
s = replace_section(
    s,
    '    private fun showRidersDialog() {',
    '    private fun showAudioRouteDialog',
    '''    private fun showRidersDialog() {
        val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }
        val meDevice = deviceLabel()
        val riderLines = linkedMapOf<String, String>()
        val secondary = activeGroup == ActiveGroup.SECONDARY

        if (secondary) {
            if (secondaryInternetNode.isConnected()) {
                secondaryInternetNode.remotePeers().forEach { peer ->
                    val device = peer.deviceName.ifBlank { "Android device" }
                    val key = "${peer.displayName}|$device".lowercase(Locale.ROOT)
                    riderLines[key] = "• ${peer.displayName}\n  $device • Secondary Internet • ${qualityGlyphs(peer.qualityBars)}"
                }
            }
        } else {
            if (internetNode.isConnected()) {
                internetNode.remotePeers().forEach { peer ->
                    val device = peer.deviceName.ifBlank { "Android device" }
                    val key = "${peer.displayName}|$device".lowercase(Locale.ROOT)
                    riderLines[key] = "• ${peer.displayName}\n  $device • Internet • ${qualityGlyphs(peer.qualityBars)}"
                }
            }
            if (meshRunning) {
                meshNode.directPeers().forEach { peer ->
                    val device = peer.deviceName.ifBlank { "Android device" }
                    val key = "${peer.displayName}|$device".lowercase(Locale.ROOT)
                    if (!riderLines.containsKey(key)) riderLines[key] = "• ${peer.displayName}\n  $device • Local mesh"
                }
            }
        }

        val code = if (secondary) secondaryRideCode ?: "—" else primaryRideCode
        val message = buildString {
            append(if (secondary) "SECONDARY GROUP • $code\n" else "PRIMARY GROUP • $code\n")
            append("YOU\n• $me\n  $meDevice\n\nCONNECTED RIDERS")
            if (riderLines.isEmpty()) append("\nWaiting for another rider…")
            else {
                append(" (${riderLines.size})\n")
                append(riderLines.values.joinToString("\n\n"))
            }
        }

        AlertDialog.Builder(this)
            .setTitle("Riders • ${riderLines.size + 1} total")
            .setMessage(message)
            .setPositiveButton("GROUPS") { _, _ -> showGroupsDialog() }
            .setNeutralButton("INVITE") { _, _ -> showLiveInviteOptions() }
            .setNegativeButton("CLOSE", null)
            .show()
    }

    private fun showGroupsDialog() {
        val secondary = secondaryRideCode
        val primaryState = if (activeGroup == ActiveGroup.PRIMARY) "ACTIVE" else "BACKGROUND"
        val secondaryState = if (secondary == null) "NOT SET" else if (activeGroup == ActiveGroup.SECONDARY) "ACTIVE" else "BACKGROUND"
        val title = "Groups • Primary $primaryRideCode"
        val message = buildString {
            append("PRIMARY  $primaryRideCode  •  $primaryState\n")
            append("SECONDARY  ${secondary ?: "—"}  •  $secondaryState\n\n")
            append("Only one group owns your microphone and speaker at a time. The other Internet group stays connected in the background. Secondary local-mesh fallback is intentionally disabled in this Beta.")
        }
        val actions = if (secondary == null) {
            arrayOf("CREATE SECOND GROUP", "JOIN SECOND GROUP", "CLOSE")
        } else {
            arrayOf(
                if (activeGroup == ActiveGroup.PRIMARY) "SWITCH TO SECONDARY • $secondary" else "SWITCH TO PRIMARY • $primaryRideCode",
                "LEAVE SECOND GROUP • $secondary",
                "CLOSE",
            )
        }

        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setItems(actions) { dialog, which ->
                if (secondary == null) {
                    when (which) {
                        0 -> createSecondaryGroup()
                        1 -> promptJoinSecondaryGroup()
                        else -> dialog.dismiss()
                    }
                } else {
                    when (which) {
                        0 -> switchActiveGroup(if (activeGroup == ActiveGroup.PRIMARY) ActiveGroup.SECONDARY else ActiveGroup.PRIMARY, "Group switched")
                        1 -> leaveSecondaryGroup()
                        else -> dialog.dismiss()
                    }
                }
            }
            .show()
    }

    private fun createSecondaryGroup() {
        var code = generateRideCode()
        while (code.equals(primaryRideCode, true)) code = generateRideCode()
        AlertDialog.Builder(this)
            .setTitle("Create second group $code?")
            .setMessage("Your primary group $primaryRideCode stays connected. The new secondary group uses Internet voice in this Beta.")
            .setNegativeButton("CANCEL", null)
            .setPositiveButton("CREATE & SWITCH") { _, _ -> startSecondaryGroup(code) }
            .show()
    }

    private fun promptJoinSecondaryGroup() {
        val input = EditText(this).apply {
            hint = "RM1234"
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))
            setHintTextColor(ContextCompat.getColor(this@MainActivity, R.color.muted))
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS
            isSingleLine = true
            setPadding(dp(18), dp(10), dp(18), dp(10))
        }
        AlertDialog.Builder(this)
            .setTitle("Join second group")
            .setMessage("Enter the ongoing RideMesh group code. Primary $primaryRideCode stays connected in the background.")
            .setView(input)
            .setNegativeButton("CANCEL", null)
            .setPositiveButton("JOIN & SWITCH") { _, _ ->
                val code = input.text?.toString().orEmpty().trim().uppercase().take(12)
                if (code.isNotBlank() && !code.equals(primaryRideCode, true)) startSecondaryGroup(code)
                else log("Second group code must be different from primary")
            }
            .show()
    }

    private fun startSecondaryGroup(codeRaw: String) {
        if (!rideStarted) return
        val code = codeRaw.trim().uppercase().replace(Regex("[^A-Z0-9_-]"), "_").take(12)
        if (code.isBlank() || code.equals(primaryRideCode, true)) return
        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }

        audioEngine.stopTransmit()
        audioEngine.resetIncomingAudio()
        secondaryInternetNode.stop()
        secondaryRideCode = code
        secondaryPeerCount = 0
        secondaryHadConnection = false
        activeGroup = ActiveGroup.SECONDARY
        speakingUntilMs.clear()
        secondaryInternetNode.start(code, rider, deviceLabel())
        updateTransportStatus()
        updateCapturePolicy()
        log("Secondary group $code connecting • primary $primaryRideCode stays connected")
    }

    private fun switchActiveGroup(group: ActiveGroup, reason: String) {
        if (!rideStarted || activeGroup == group) return
        if (group == ActiveGroup.SECONDARY && secondaryRideCode == null) return
        audioEngine.stopTransmit()
        audioEngine.resetIncomingAudio()
        speakingUntilMs.clear()
        activeGroup = group
        updateTransportStatus()
        updateCapturePolicy()
        log("$reason • ${if (group == ActiveGroup.PRIMARY) "primary $primaryRideCode" else "secondary ${secondaryRideCode ?: "—"}"}")
    }

    private fun leaveSecondaryGroup() {
        if (activeGroup == ActiveGroup.SECONDARY) switchActiveGroup(ActiveGroup.PRIMARY, "Returned to primary")
        secondaryInternetNode.stop()
        secondaryRideCode = null
        secondaryPeerCount = 0
        secondaryHadConnection = false
        updateTransportStatus()
        log("Second group closed • primary continues")
    }

    private fun primaryPathAvailable(): Boolean = internetNode.isConnected() || directPeerCount > 0

    private fun currentInviteCode(): String = if (rideStarted && activeGroup == ActiveGroup.SECONDARY) {
        secondaryRideCode ?: primaryRideCode
    } else if (rideStarted) {
        primaryRideCode
    } else {
        normalizedRideCode()
    }

'''
)

# Status dialog shows both sessions.
s = replace_section(
    s,
    '    private fun showRideStatusDialog() {',
    '    private fun openWhatsAppBugReport',
    '''    private fun showRideStatusDialog() {
        val primaryPath = when {
            internetNode.isConnected() -> "Internet"
            directPeerCount > 0 -> "Local mesh"
            else -> "Reconnecting"
        }
        val secondary = secondaryRideCode
        val secondaryPath = when {
            secondary == null -> "Not configured"
            secondaryInternetNode.isConnected() -> "Internet connected"
            else -> "Internet reconnecting"
        }

        AlertDialog.Builder(this)
            .setTitle("Ride status")
            .setMessage(
                "Active voice: ${if (activeGroup == ActiveGroup.PRIMARY) "PRIMARY $primaryRideCode" else "SECONDARY ${secondary ?: "—"}"}\n\n" +
                    "Primary $primaryRideCode: $primaryPath\n" +
                    "Primary Internet riders: ${if (internetNode.isConnected()) internetPeerCount + 1 else 0}\n" +
                    "Direct local peers: $directPeerCount\n\n" +
                    "Secondary ${secondary ?: "—"}: $secondaryPath\n" +
                    "Secondary riders: ${if (secondaryInternetNode.isConnected()) secondaryPeerCount + 1 else 0}\n\n" +
                    "Audio: ${binding.audioTile.text}\nNoise reduction: ON\nPower: ${binding.powerTile.text}\nAuto reconnect: ON"
            )
            .setPositiveButton("GROUPS") { _, _ -> showGroupsDialog() }
            .setNeutralButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }
            .setNegativeButton("CLOSE", null)
            .show()
    }

'''
)
s = replace_once(s, '            append("Ride code: ${normalizedRideCode()}\\n")', '            append("Active ride: ${currentInviteCode()}\\n")\n            if (secondaryRideCode != null) append("Primary: $primaryRideCode • Secondary: $secondaryRideCode\\n")')
s = replace_once(
    s,
    '        if (::internetNode.isInitialized && !rideStarted) internetNode.stop()\n        if (!rideStarted && ::audioEngine.isInitialized) audioEngine.release()',
    '        if (::internetNode.isInitialized && !rideStarted) internetNode.stop()\n        if (::secondaryInternetNode.isInitialized && !rideStarted) secondaryInternetNode.stop()\n        if (!rideStarted && ::audioEngine.isInitialized) audioEngine.release()'
)
p.write_text(s)

# Active UI: exact logo header, compact full-width LIVE panel with ride code + END at the same level,
# and the approved large rider tile grid. Keep the rest of setup screens intact.
p = Path("app/src/main/res/layout/activity_main.xml")
s = p.read_text()
# Home logo/settings proportions and two side-by-side main actions.
s = replace_once(s, 'android:layout_height="66dp"\n                android:gravity="center_vertical"', 'android:layout_height="78dp"\n                android:gravity="center_vertical"')
s = replace_once(s, 'android:layout_width="154dp"\n                    android:layout_height="62dp"', 'android:layout_width="218dp"\n                    android:layout_height="76dp"')
s = replace_once(s, 'android:paddingStart="10dp"\n                    android:paddingEnd="10dp"', 'android:layout_marginTop="6dp"\n                    android:paddingStart="8dp"\n                    android:paddingEnd="8dp"')

home_actions_start = '            <com.google.android.material.button.MaterialButton\n                android:id="@+id/createRide"'
status_card = '            <LinearLayout\n                android:layout_width="match_parent"\n                android:layout_height="wrap_content"\n                android:layout_marginTop="22dp"\n                android:background="@drawable/status_card_bg"'
new_actions = '''            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="60dp"
                android:layout_marginTop="22dp"
                android:orientation="horizontal">

                <com.google.android.material.button.MaterialButton
                    android:id="@+id/createRide"
                    android:layout_width="0dp"
                    android:layout_height="58dp"
                    android:layout_marginEnd="6dp"
                    android:layout_weight="1"
                    android:text="CREATE A RIDE"
                    android:textColor="#00201D"
                    android:textSize="11sp"
                    android:textStyle="bold"
                    app:backgroundTint="@color/accent"
                    app:cornerRadius="16dp"
                    app:icon="@drawable/ic_add_ride"
                    app:iconGravity="textStart"
                    app:iconPadding="6dp"
                    app:iconTint="#00201D" />

                <com.google.android.material.button.MaterialButton
                    android:id="@+id/joinRide"
                    style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                    android:layout_width="0dp"
                    android:layout_height="58dp"
                    android:layout_marginStart="6dp"
                    android:layout_weight="1"
                    android:text="JOIN A RIDE"
                    android:textColor="@color/white"
                    android:textSize="11sp"
                    android:textStyle="bold"
                    app:cornerRadius="16dp"
                    app:icon="@drawable/ic_join_ride"
                    app:iconGravity="textStart"
                    app:iconPadding="6dp"
                    app:iconTint="@color/white"
                    app:strokeColor="@color/accent"
                    app:strokeWidth="1dp" />
            </LinearLayout>

'''
s = replace_section(s, home_actions_start, status_card, new_actions)

active_marker = '    <!-- ACTIVE RIDE -->'
active_ui = '''    <!-- ACTIVE RIDE -->
    <LinearLayout
        android:id="@+id/screenActive"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:orientation="vertical"
        android:paddingStart="18dp"
        android:paddingTop="12dp"
        android:paddingEnd="18dp"
        android:paddingBottom="12dp"
        android:visibility="gone">

        <ImageView
            android:layout_width="205dp"
            android:layout_height="70dp"
            android:contentDescription="RideMesh by Autopilot India"
            android:scaleType="fitStart"
            android:src="@drawable/ridemesh_logo_exact" />

        <TextView
            android:id="@+id/riderCount"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginTop="5dp"
            android:fontFamily="sans-serif-condensed"
            android:gravity="center"
            android:text="RIDE ACTIVE"
            android:textColor="@color/white"
            android:textSize="25sp"
            android:textStyle="bold" />

        <TextView
            android:id="@+id/meshStatus"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginTop="3dp"
            android:gravity="center"
            android:text="CONNECTING…"
            android:textColor="@color/accent"
            android:textSize="11sp"
            android:textStyle="bold" />

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="50dp"
            android:layout_marginTop="12dp"
            android:gravity="center"
            android:orientation="horizontal">

            <TextView
                android:id="@+id/networkTile"
                android:layout_width="0dp"
                android:layout_height="42dp"
                android:layout_marginEnd="5dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="CONNECTING"
                android:textColor="@color/accent"
                android:textSize="10sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/audioTile"
                android:layout_width="0dp"
                android:layout_height="42dp"
                android:layout_marginHorizontal="5dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="VOICE CLEAN"
                android:textColor="@color/white"
                android:textSize="10sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/powerTile"
                android:layout_width="0dp"
                android:layout_height="42dp"
                android:layout_marginStart="5dp"
                android:layout_weight="1"
                android:background="@drawable/panel_bg"
                android:gravity="center"
                android:text="SMART POWER"
                android:textColor="@color/green"
                android:textSize="10sp"
                android:textStyle="bold" />
        </LinearLayout>

        <LinearLayout
            android:id="@+id/handsFreeIndicator"
            android:layout_width="match_parent"
            android:layout_height="82dp"
            android:layout_marginTop="11dp"
            android:background="@drawable/live_panel_bg"
            android:gravity="center_vertical"
            android:orientation="horizontal"
            android:paddingStart="16dp"
            android:paddingEnd="8dp">

            <LinearLayout
                android:layout_width="0dp"
                android:layout_height="match_parent"
                android:layout_weight="1"
                android:gravity="center_vertical"
                android:orientation="vertical">

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:fontFamily="sans-serif-condensed"
                    android:letterSpacing="0.07"
                    android:text="LIVE"
                    android:textColor="@color/accent"
                    android:textSize="20sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="HANDS-FREE INTERCOM"
                    android:textColor="@color/white"
                    android:textSize="10sp"
                    android:textStyle="bold" />

                <TextView
                    android:id="@+id/audioStatus"
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="3dp"
                    android:ellipsize="end"
                    android:maxLines="1"
                    android:text="VOICE-ACTIVATED • NOISE GUARD"
                    android:textColor="@color/muted"
                    android:textSize="7.5sp" />
            </LinearLayout>

            <View
                android:layout_width="1dp"
                android:layout_height="48dp"
                android:layout_marginHorizontal="8dp"
                android:background="@color/border_strong" />

            <LinearLayout
                android:id="@+id/groupSwitcher"
                android:layout_width="76dp"
                android:layout_height="match_parent"
                android:clickable="true"
                android:focusable="true"
                android:foreground="?attr/selectableItemBackground"
                android:gravity="center"
                android:orientation="vertical">

                <TextView
                    android:id="@+id/activeGroupLabel"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:text="PRIMARY"
                    android:textColor="@color/muted"
                    android:textSize="7.5sp"
                    android:textStyle="bold" />

                <TextView
                    android:id="@+id/activeRideCode"
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="2dp"
                    android:text="RM0000"
                    android:textColor="@color/white"
                    android:textSize="14sp"
                    android:textStyle="bold" />
            </LinearLayout>

            <View
                android:layout_width="1dp"
                android:layout_height="48dp"
                android:layout_marginHorizontal="5dp"
                android:background="@color/border_strong" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeStop"
                style="@style/Widget.MaterialComponents.Button.TextButton"
                android:layout_width="64dp"
                android:layout_height="56dp"
                android:minWidth="0dp"
                android:text="END"
                android:textColor="#FF554D"
                android:textSize="13sp"
                android:textStyle="bold" />
        </LinearLayout>

        <GridLayout
            android:id="@+id/riderGrid"
            android:layout_width="match_parent"
            android:layout_height="0dp"
            android:layout_marginTop="10dp"
            android:layout_weight="1"
            android:alignmentMode="alignMargins"
            android:columnCount="3"
            android:gravity="center"
            android:orientation="horizontal"
            android:rowCount="2"
            android:useDefaultMargins="false" />

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="62dp"
            android:orientation="horizontal">

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeRiders"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginEnd="4dp"
                android:layout_weight="1"
                android:text="RIDERS"
                android:textColor="@color/white"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/border" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeInvite"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginHorizontal="4dp"
                android:layout_weight="1"
                android:text="INVITE"
                android:textColor="@color/accent"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/accent" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeAudio"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginHorizontal="4dp"
                android:layout_weight="1"
                android:text="AUDIO"
                android:textColor="@color/white"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/border" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/activeStatus"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="0dp"
                android:layout_height="54dp"
                android:layout_marginStart="4dp"
                android:layout_weight="1"
                android:text="STATUS"
                android:textColor="@color/white"
                android:textSize="9sp"
                app:cornerRadius="12dp"
                app:strokeColor="@color/border" />
        </LinearLayout>
    </LinearLayout>

</FrameLayout>
'''
s = s[:s.index(active_marker)] + active_ui
p.write_text(s)

print("Beta 1.3 dual-group/UI patch applied")
