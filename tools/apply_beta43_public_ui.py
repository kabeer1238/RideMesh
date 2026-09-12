from pathlib import Path
import re

ROOT = Path('.')

def replace_once(text, old, new, label):
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f'{label}: anchor not found')
    return text.replace(old, new, 1)

def sub_once(text, pattern, replacement, label):
    if replacement in text:
        return text
    out, count = re.subn(pattern, lambda m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: pattern count {count}')
    return out

p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

s = replace_once(s, 'import android.os.Looper\n', 'import android.os.Looper\nimport android.text.InputType\nimport android.util.Patterns\n', 'email imports 1')
s = replace_once(s, 'import android.widget.GridLayout\n', 'import android.widget.EditText\nimport android.widget.GridLayout\n', 'email imports 2')

s = replace_once(
    s,
    '''        refreshBetaAccessUi(showWarning = true)\n        updateMuteUi()\n    }\n\n    private fun showScreen''',
    '''        refreshBetaAccessUi(showWarning = true)\n        updateMuteUi()\n        binding.logView.visibility = View.GONE\n        mainHandler.post { ensureUserEmail() }\n    }\n\n    private fun savedUserEmail(): String =\n        prefs.getString(USER_EMAIL_KEY, "").orEmpty().trim()\n\n    private fun ensureUserEmail(): Boolean {\n        val email = savedUserEmail()\n        if (Patterns.EMAIL_ADDRESS.matcher(email).matches()) return true\n        showEmailEntryDialog(required = true)\n        return false\n    }\n\n    private fun showEmailEntryDialog(required: Boolean = false) {\n        val input = EditText(this).apply {\n            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS\n            hint = "you@example.com"\n            setText(savedUserEmail())\n            setSelectAllOnFocus(true)\n            setSingleLine(true)\n        }\n\n        val dialog = AlertDialog.Builder(this)\n            .setTitle(if (savedUserEmail().isBlank()) "Welcome to RideMesh" else "Update email")\n            .setMessage(\n                if (required)\n                    "Enter your email to continue. No OTP or password is required in this beta."\n                else\n                    "Update the email saved on this device. No OTP or password is required."\n            )\n            .setView(input)\n            .setCancelable(!required)\n            .setPositiveButton("SAVE", null)\n            .apply {\n                if (!required) setNegativeButton("CANCEL", null)\n            }\n            .create()\n\n        dialog.setOnShowListener {\n            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {\n                val email = input.text?.toString().orEmpty().trim().lowercase()\n                if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {\n                    input.error = "Enter a valid email address"\n                    input.requestFocus()\n                } else {\n                    prefs.edit().putString(USER_EMAIL_KEY, email).apply()\n                    dialog.dismiss()\n                }\n            }\n        }\n        dialog.show()\n    }\n\n    private fun showScreen''',
    'email profile flow',
)

s = replace_once(
    s,
    '''    private fun startRideNow() {\n        if (rideStarted || !ensureBetaUsable()) return\n\n        setMicMuted(false)\n        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }\n        val code = normalizedRideCode()\n''',
    '''    private fun startRideNow() {\n        if (rideStarted || !ensureBetaUsable()) return\n        if (!ensureUserEmail()) return\n\n        val code = normalizedRideCode()\n        if (!isValidRideCode(code)) {\n            binding.rideCode.error = "Use 5–12 letters and numbers only"\n            binding.rideCode.requestFocus()\n            return\n        }\n\n        setMicMuted(false)\n        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }\n''',
    'start validation',
)

s = replace_once(
    s,
    '        val code = normalizedRideCode()\n        binding.rideCode.setText(code)\n        saveSettings()\n\n        try {\n            val bitmap = buildRideQrBitmap(code)',
    '        val code = validatedRideCodeOrNull() ?: return\n        binding.rideCode.setText(code)\n        saveSettings()\n\n        try {\n            val bitmap = buildRideQrBitmap(code)',
    'show QR validation',
)

s = replace_once(s, '    private fun shareRideQr() {\n        val code = normalizedRideCode()\n', '    private fun shareRideQr() {\n        val code = validatedRideCodeOrNull() ?: return\n', 'share QR validation')

s = sub_once(
    s,
    r'''    private fun parseRideQr\(raw: String\): String\? = runCatching \{.*?    \}\.getOrNull\(\)''',
    '''    private fun parseRideQr(raw: String): String? = runCatching {\n        val uri = Uri.parse(raw)\n        if (!uri.scheme.equals("ridemesh", true) || !uri.host.equals("join", true)) {\n            return@runCatching null\n        }\n        uri.getQueryParameter("ride")\n            ?.trim()\n            ?.uppercase()\n            ?.take(12)\n            ?.takeIf(::isValidRideCode)\n    }.getOrNull()''',
    'QR code parser',
)

s = sub_once(
    s,
    r'''    private fun normalizedRideCode\(\): String = binding\.rideCode\.text.*?    private fun generateRideCode\(\): String = .*?\n''',
    '''    private fun normalizedRideCode(): String = binding.rideCode.text\n        ?.toString()\n        .orEmpty()\n        .trim()\n        .uppercase()\n        .take(12)\n\n    private fun isValidRideCode(code: String): Boolean =\n        code.length in 5..12 && code.all { it in 'A'..'Z' || it in '0'..'9' }\n\n    private fun validatedRideCodeOrNull(): String? {\n        val code = normalizedRideCode()\n        if (isValidRideCode(code)) return code\n        binding.rideCode.error = "Use 5–12 letters and numbers only"\n        binding.rideCode.requestFocus()\n        return null\n    }\n\n    private fun generateRideCode(): String = "RM" + Random.nextInt(1000, 9999)\n''',
    'ride code rules',
)

s = sub_once(
    s,
    r'''    private fun showRideStatusDialog\(\) \{.*?    \}\n\n    private fun openWhatsAppBugReport''',
    '''    private fun showRideStatusDialog() {\n        val diag = internetNode.diagnostics()\n        val connection = when {\n            diag.voicePeersConnected > 0 -> "Connected"\n            diag.signalingConnected -> "Ready"\n            else -> "Reconnecting…"\n        }\n        val voice = when {\n            micMuted -> "Muted"\n            diag.voicePeersConnected > 0 -> "Connected"\n            else -> "Ready"\n        }\n        val quality = when {\n            diag.voicePeersConnected >= 1 -> "Good"\n            diag.signalingConnected -> "Ready"\n            else -> "Checking"\n        }\n        val riders = (diag.knownRiders + 1).coerceAtLeast(1)\n\n        AlertDialog.Builder(this)\n            .setTitle("Ride Status")\n            .setMessage(\n                "Connection: $connection\\n" +\n                    "Voice: $voice\\n" +\n                    "Riders: $riders connected\\n" +\n                    "Microphone: ${if (micMuted) "Muted" else "Active"}\\n" +\n                    "Voice quality: $quality\\n\\n" +\n                    betaStatusSentence()\n            )\n            .setPositiveButton("WHATSAPP SUPPORT") { _, _ -> openWhatsAppBugReport() }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n    private fun openWhatsAppBugReport''',
    'public ride status',
)

s = sub_once(
    s,
    r'''    private fun openWhatsAppBugReport\(\) \{.*?    private fun openRideMeshCommunity\(\) \{.*?    \}\n''',
    '''    private fun openWhatsAppBugReport() {\n        openExternalUri(BUG_REPORT_GROUP_URL, "Could not open RideMesh WhatsApp group")\n    }\n\n    private fun openRideMeshCommunity() {\n        openExternalUri(BUG_REPORT_GROUP_URL, "Could not open RideMesh WhatsApp group")\n    }\n''',
    'WhatsApp group support only',
)

s = sub_once(
    s,
    r'''    private fun showSettingsAndHelpDialog\(\) \{.*?    \}\n\n    private fun ensureBetaFirstLaunch''',
    '''    private fun showSettingsAndHelpDialog() {\n        val email = savedUserEmail().ifBlank { "Not set" }\n        AlertDialog.Builder(this)\n            .setTitle("RideMesh settings & support")\n            .setMessage(\n                "Email: $email\\n\\n" +\n                    "RideMesh keeps your group connected with hands-free voice. " +\n                    "It automatically yields audio when another phone or calling app needs it, then resumes afterward.\\n\\n" +\n                    betaStatusSentence()\n            )\n            .setPositiveButton("WHATSAPP GROUP") { _, _ -> openWhatsAppBugReport() }\n            .setNeutralButton("CHANGE EMAIL") { _, _ -> showEmailEntryDialog(required = false) }\n            .setNegativeButton("CLOSE", null)\n            .show()\n    }\n\n    private fun ensureBetaFirstLaunch''',
    'public settings',
)

s = sub_once(
    s,
    r'''    private fun showTransportModeDialog\(\) \{.*?    \}\n\n    private fun showMeshLabRoleDialog''',
    '''    private fun showTransportModeDialog() {\n        AlertDialog.Builder(this)\n            .setTitle("Voice connection")\n            .setMessage("RideMesh automatically manages the voice connection while your ride is active.")\n            .setPositiveButton("OK", null)\n            .show()\n    }\n\n    private fun showMeshLabRoleDialog''',
    'hide engine info',
)

s = sub_once(
    s,
    r'''    private fun updateTransportStatus\(\) \{.*?    \}\n\n    private fun markRiderSpeaking''',
    '''    private fun updateTransportStatus() {\n        if (!rideStarted) return\n        val diag = internetNode.diagnostics()\n\n        binding.networkTile.text = when {\n            diag.voicePeersConnected > 0 -> "CONNECTED"\n            diag.signalingConnected -> "READY"\n            else -> "CONNECTING"\n        }\n        binding.riderCount.text = "RIDE ACTIVE"\n        binding.meshStatus.text = when {\n            diag.voicePeersConnected > 0 ->\n                "VOICE CONNECTED • ${diag.voicePeersConnected + 1} RIDERS"\n            diag.signalingConnected -> "VOICE READY • WAITING FOR RIDERS"\n            else -> "RECONNECTING…"\n        }\n        binding.homeNetworkStatus.text = when {\n            diag.voicePeersConnected > 0 -> "Voice\\nConnected"\n            diag.signalingConnected -> "Internet\\nReady"\n            else -> "Connection\\nReady"\n        }\n\n        val visibleRiderTotal = if (internetNode.isConnected()) internetPeerCount + 1 else 1\n        binding.activeRiders.text = "RIDERS $visibleRiderTotal"\n        renderRiderGrid()\n        applyPowerUi()\n    }\n\n    private fun markRiderSpeaking''',
    'public transport status',
)

s = sub_once(
    s,
    r'''    private fun updateCapturePolicy\(\) \{.*?    \}\n\n    private fun startRideServiceSafely''',
    '''    private fun updateCapturePolicy() {\n        if (!rideStarted) return\n        val status = when {\n            micMuted -> "MIC MUTED • LISTENING ONLY"\n            internetNode.voicePeerCount() > 0 -> "VOICE CONNECTED • MIC LIVE"\n            internetNode.isConnected() -> "VOICE READY • WAITING FOR RIDERS"\n            else -> "CONNECTING • MIC READY"\n        }\n        updateAudioUi(status)\n    }\n\n    private fun startRideServiceSafely''',
    'public audio status',
)

s = sub_once(s, r'''    private fun transportModeLabel\(\): String = .*?\n''', '    private fun transportModeLabel(): String = "INTERNET VOICE"\n', 'public transport label')

s = sub_once(
    s,
    r'''    private fun log\(message: String\) \{.*?    \}\n''',
    '''    private fun log(message: String) {\n        // Public build intentionally suppresses verbose transport / infrastructure diagnostics.\n    }\n''',
    'suppress public logs',
)

s = s.replace('        private const val SUPPORT_WHATSAPP = "919188664823"\n', '')
s = s.replace('        private const val COMMUNITY_URL = "https://chat.whatsapp.com/GTH7FA1uTUFGRXElnfDfdE"\n', '')
if 'private const val USER_EMAIL_KEY' not in s:
    s = replace_once(
        s,
        '        private const val BETA_WARNING_BUCKET_KEY = "beta_warning_bucket_v2"\n',
        '        private const val BETA_WARNING_BUCKET_KEY = "beta_warning_bucket_v2"\n        private const val USER_EMAIL_KEY = "user_email_v1"\n',
        'email pref key',
    )

p.write_text(s)

p = ROOT / 'app/src/main/res/layout/activity_main.xml'
x = p.read_text()
x = x.replace(
    'android:text="RideMesh uses low-latency WebRTC Internet voice with Opus for clear group communication across distance."',
    'android:text="RideMesh keeps your riding group connected with clear hands-free voice across distance."',
)
x = x.replace('android:text="WebRTC Voice\nReady"', 'android:text="Voice\nReady"')
x = x.replace('android:hint="RM4825"', 'android:hint="RM4825 • minimum 5 characters"')
p.write_text(x)

print('Beta4.3 public UI/privacy patch applied')