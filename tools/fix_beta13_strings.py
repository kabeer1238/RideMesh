from pathlib import Path


def replace_section(text: str, start: str, end: str, replacement: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + replacement + text[j:]

p = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = p.read_text()

s = replace_section(
    s,
    '    private fun showRidersDialog() {',
    '    private fun showAudioRouteDialog',
    r'''    private fun showRidersDialog() {
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
                    if (!riderLines.containsKey(key)) {
                        riderLines[key] = "• ${peer.displayName}\n  $device • Local mesh"
                    }
                }
            }
        }

        val code = if (secondary) secondaryRideCode ?: "—" else primaryRideCode
        val message = buildString {
            appendLine(if (secondary) "SECONDARY GROUP • $code" else "PRIMARY GROUP • $code")
            appendLine("YOU")
            appendLine("• $me")
            appendLine("  $meDevice")
            appendLine()
            append("CONNECTED RIDERS")
            if (riderLines.isEmpty()) {
                appendLine()
                append("Waiting for another rider…")
            } else {
                appendLine(" (${riderLines.size})")
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
            appendLine("PRIMARY  $primaryRideCode  •  $primaryState")
            appendLine("SECONDARY  ${secondary ?: "—"}  •  $secondaryState")
            appendLine()
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
                        0 -> switchActiveGroup(
                            if (activeGroup == ActiveGroup.PRIMARY) ActiveGroup.SECONDARY else ActiveGroup.PRIMARY,
                            "Group switched",
                        )
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

s = replace_section(
    s,
    '    private fun showRideStatusDialog() {',
    '    private fun openWhatsAppBugReport',
    r'''    private fun showRideStatusDialog() {
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

        val message = buildString {
            appendLine("Active voice: ${if (activeGroup == ActiveGroup.PRIMARY) "PRIMARY $primaryRideCode" else "SECONDARY ${secondary ?: "—"}"}")
            appendLine()
            appendLine("Primary $primaryRideCode: $primaryPath")
            appendLine("Primary Internet riders: ${if (internetNode.isConnected()) internetPeerCount + 1 else 0}")
            appendLine("Direct local peers: $directPeerCount")
            appendLine()
            appendLine("Secondary ${secondary ?: "—"}: $secondaryPath")
            appendLine("Secondary riders: ${if (secondaryInternetNode.isConnected()) secondaryPeerCount + 1 else 0}")
            appendLine()
            appendLine("Audio: ${binding.audioTile.text}")
            appendLine("Noise reduction: ON")
            appendLine("Power: ${binding.powerTile.text}")
            append("Auto reconnect: ON")
        }

        AlertDialog.Builder(this)
            .setTitle("Ride status")
            .setMessage(message)
            .setPositiveButton("GROUPS") { _, _ -> showGroupsDialog() }
            .setNeutralButton("REPORT BUG") { _, _ -> openWhatsAppBugReport() }
            .setNegativeButton("CLOSE", null)
            .show()
    }

'''
)

p.write_text(s)
print("Beta 1.3 generated Kotlin strings fixed")
