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
    out, count = re.subn(pattern, lambda m: replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f'{label}: pattern count {count}')
    return out


# Version only: vc13 APK test candidate. Keep vc12 crash-fix release settings unchanged.
p = ROOT / 'app/build.gradle.kts'
s = p.read_text()
s = s.replace('versionCode = 12', 'versionCode = 13')
s = s.replace('versionName = "1.0.0-beta4.4.1-crashfix"', 'versionName = "1.0.0-beta4.5-themed-ui"')
p.write_text(s)


p = ROOT / 'app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt'
s = p.read_text()

# Dialog/theme imports.
s = replace_once(s, 'import android.app.AlertDialog\n', 'import android.app.AlertDialog\nimport android.app.Dialog\n', 'dialog import')
s = replace_once(s, 'import android.graphics.drawable.GradientDrawable\n', 'import android.graphics.drawable.ColorDrawable\nimport android.graphics.drawable.GradientDrawable\n', 'color drawable import')
s = replace_once(s, 'import android.widget.LinearLayout\n', 'import android.widget.LinearLayout\nimport android.widget.ScrollView\n', 'scroll view import')

# -----------------------------------------------------------------------------
# Email -> initial rider display name. Never expose the email to peers.
# Existing custom rider names are preserved when email is changed later.
# -----------------------------------------------------------------------------
s = sub_once(
    s,
    r'''    private fun saveEmailProfile\(\) \{.*?    \}\n\n    private fun showScreen''',
    '''    private fun riderNameFromEmail(email: String): String {\n        val local = email.substringBefore('@')\n            .replace('.', ' ')\n            .replace('_', ' ')\n            .replace('-', ' ')\n            .trim()\n        val words = local.split(Regex("\\\\s+")).filter { it.isNotBlank() }\n        val display = words.joinToString(" ") { word ->\n            word.lowercase(Locale.ROOT).replaceFirstChar { ch ->\n                if (ch.isLowerCase()) ch.titlecase(Locale.ROOT) else ch.toString()\n            }\n        }.trim()\n        return display.ifBlank { "Rider" }.take(24)\n    }\n\n    private fun saveEmailProfile() {\n        val email = binding.emailInput.text?.toString().orEmpty().trim().lowercase()\n        if (!Patterns.EMAIL_ADDRESS.matcher(email).matches()) {\n            binding.emailInput.error = "Enter a valid email address"\n            binding.emailInput.requestFocus()\n            return\n        }\n\n        val currentName = binding.riderName.text?.toString().orEmpty().trim()\n        val storedName = prefs.getString("rider", "").orEmpty().trim()\n        val shouldCreateName = currentName.isBlank() || currentName.equals("Rider", true) || storedName.isBlank() || storedName.equals("Rider", true)\n        val editor = prefs.edit().putString(USER_EMAIL_KEY, email)\n        if (shouldCreateName) {\n            val generatedName = riderNameFromEmail(email)\n            binding.riderName.setText(generatedName)\n            editor.putString("rider", generatedName)\n        }\n        editor.apply()\n        binding.screenEmail.visibility = View.GONE\n    }\n\n    private fun showScreen''',
    'email derived rider name',
)

# -----------------------------------------------------------------------------
# Unified RideMesh panel system: black / cyan / rounded cards, no default Android
# dialogs for the five rider-facing pages requested by the product owner.
# -----------------------------------------------------------------------------
helpers = r'''    private fun panelCardBackground(highlight: Boolean = false): GradientDrawable =\n        GradientDrawable().apply {\n            cornerRadius = dp(16).toFloat()\n            setColor(Color.parseColor(if (highlight) "#0B1716" else "#0A0F0F"))\n            setStroke(\n                dp(1),\n                ContextCompat.getColor(this@MainActivity, if (highlight) R.color.accent else R.color.border)\n            )\n        }\n\n    private fun showRideMeshPanel(\n        title: String,\n        subtitle: String? = null,\n        buildContent: (LinearLayout, Dialog) -> Unit,\n    ) {\n        val dialog = Dialog(this)\n        val accent = ContextCompat.getColor(this, R.color.accent)\n        val white = ContextCompat.getColor(this, R.color.white)\n        val muted = ContextCompat.getColor(this, R.color.muted)\n\n        val shell = LinearLayout(this).apply {\n            orientation = LinearLayout.VERTICAL\n            setPadding(dp(20), dp(20), dp(20), dp(18))\n            background = GradientDrawable().apply {\n                cornerRadius = dp(26).toFloat()\n                setColor(Color.parseColor("#050808"))\n                setStroke(dp(1), Color.parseColor("#19302E"))\n            }\n        }\n\n        shell.addView(TextView(this).apply {\n            text = "RIDE MESH  •  BETA"\n            textSize = 10f\n            letterSpacing = 0.16f\n            setTypeface(Typeface.DEFAULT, Typeface.BOLD)\n            setTextColor(accent)\n        })\n\n        shell.addView(TextView(this).apply {\n            text = title\n            textSize = 27f\n            setTypeface(Typeface.DEFAULT, Typeface.BOLD)\n            setTextColor(white)\n        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {\n            topMargin = dp(8)\n        })\n\n        if (!subtitle.isNullOrBlank()) {\n            shell.addView(TextView(this).apply {\n                text = subtitle\n                textSize = 13f\n                setTextColor(muted)\n                setLineSpacing(0f, 1.16f)\n            }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {\n                topMargin = dp(5)\n                bottomMargin = dp(14)\n            })\n        } else {\n            shell.addView(View(this), LinearLayout.LayoutParams(1, dp(12)))\n        }\n\n        val body = LinearLayout(this).apply {\n            orientation = LinearLayout.VERTICAL\n        }\n        val scroll = ScrollView(this).apply {\n            isFillViewport = false\n            addView(body, ScrollView.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))\n        }\n        shell.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))\n\n        buildContent(body, dialog)\n\n        addPanelButton(body, "CLOSE", primary = false) { dialog.dismiss() }\n\n        dialog.setContentView(shell)\n        dialog.setCancelable(true)\n        dialog.window?.apply {\n            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))\n            addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)\n            attributes = attributes.apply { dimAmount = 0.82f }\n        }\n        dialog.show()\n        dialog.window?.setLayout(\n            (resources.displayMetrics.widthPixels * 0.94f).toInt(),\n            ViewGroup.LayoutParams.WRAP_CONTENT,\n        )\n    }\n\n    private fun addPanelSection(parent: LinearLayout, label: String) {\n        parent.addView(TextView(this).apply {\n            text = label.uppercase(Locale.ROOT)\n            textSize = 10f\n            letterSpacing = 0.12f\n            setTypeface(Typeface.DEFAULT, Typeface.BOLD)\n            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))\n        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {\n            topMargin = dp(10)\n            bottomMargin = dp(7)\n        })\n    }\n\n    private fun addPanelInfo(parent: LinearLayout, label: String, value: String, highlight: Boolean = false) {\n        val card = LinearLayout(this).apply {\n            orientation = LinearLayout.VERTICAL\n            setPadding(dp(14), dp(12), dp(14), dp(12))\n            background = panelCardBackground(highlight)\n        }\n        card.addView(TextView(this).apply {\n            text = label.uppercase(Locale.ROOT)\n            textSize = 9.5f\n            letterSpacing = 0.08f\n            setTypeface(Typeface.DEFAULT, Typeface.BOLD)\n            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))\n        })\n        card.addView(TextView(this).apply {\n            text = value\n            textSize = 15f\n            setTypeface(Typeface.DEFAULT, Typeface.BOLD)\n            setTextColor(ContextCompat.getColor(this@MainActivity, if (highlight) R.color.accent else R.color.white))\n        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {\n            topMargin = dp(4)\n        })\n        parent.addView(card, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {\n            bottomMargin = dp(8)\n        })\n    }\n\n    private fun addPanelButton(parent: LinearLayout, label: String, primary: Boolean = true, onClick: () -> Unit) {\n        val accent = ContextCompat.getColor(this, R.color.accent)\n        val panel = ContextCompat.getColor(this, R.color.panel2)\n        val button = MaterialButton(this).apply {\n            text = label\n            textSize = 11.5f\n            setTypeface(Typeface.DEFAULT, Typeface.BOLD)\n            cornerRadius = dp(14)\n            strokeWidth = dp(1)\n            strokeColor = ColorStateList.valueOf(if (primary) accent else ContextCompat.getColor(this@MainActivity, R.color.border))\n            backgroundTintList = ColorStateList.valueOf(if (primary) accent else panel)\n            setTextColor(if (primary) Color.BLACK else ContextCompat.getColor(this@MainActivity, R.color.white))\n            setOnClickListener { onClick() }\n        }\n        parent.addView(button, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52)).apply {\n            topMargin = dp(6)\n        })\n    }\n\n    private fun showRiderNameEditor() {\n        showRideMeshPanel("RIDER NAME", "This is the name other riders see. Your email is never shown to the group.") { body, dialog ->\n            val input = EditText(this).apply {\n                setText(binding.riderName.text?.toString().orEmpty())\n                hint = "Rider name"\n                setSingleLine(true)\n                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_WORDS\n                setTextColor(ContextCompat.getColor(this@MainActivity, R.color.white))\n                setHintTextColor(ContextCompat.getColor(this@MainActivity, R.color.faint))\n                backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this@MainActivity, R.color.accent))\n            }\n            body.addView(input, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56)).apply {\n                bottomMargin = dp(8)\n            })\n            addPanelButton(body, "SAVE RIDER NAME") {\n                val name = input.text?.toString().orEmpty().trim().take(24)\n                if (name.isBlank()) {\n                    input.error = "Enter a rider name"\n                } else {\n                    binding.riderName.setText(name)\n                    prefs.edit().putString("rider", name).apply()\n                    dialog.dismiss()\n                }\n            }\n        }\n    }\n\n'''

if 'private fun showRideMeshPanel(' not in s:
    anchor = '    private fun showRidersDialog() {'
    if anchor not in s:
        raise SystemExit('themed helper anchor not found')
    s = s.replace(anchor, helpers + anchor, 1)

# Invite page.
s = sub_once(
    s,
    r'''    private fun showLiveInviteOptions\(\) \{.*?    \}\n\n    private fun buildRideQrBitmap''',
    '''    private fun showLiveInviteOptions() {\n        val code = validatedRideCodeOrNull() ?: return\n        showRideMeshPanel(\n            "INVITE RIDERS",\n            "Share this Ride Code or QR. Riders use Join a Ride and the same code to enter your group.",\n        ) { body, dialog ->\n            addPanelSection(body, "Ride code")\n            addPanelInfo(body, "Current code", code, highlight = true)\n            addPanelButton(body, "SHOW QR CODE") {\n                dialog.dismiss()\n                showRideQr()\n            }\n            addPanelButton(body, "SHARE QR CODE", primary = false) {\n                dialog.dismiss()\n                shareRideQr()\n            }\n        }\n    }\n\n    private fun buildRideQrBitmap''',
    'themed invite page',
)

# QR page within Invite.
s = sub_once(
    s,
    r'''    private fun showRideQr\(\) \{.*?    \}\n\n    private fun shareRideQr''',
    '''    private fun showRideQr() {\n        val code = validatedRideCodeOrNull() ?: return\n        binding.rideCode.setText(code)\n        saveSettings()\n\n        try {\n            val bitmap = buildRideQrBitmap(code)\n            showRideMeshPanel("RIDE QR", "Scan to join RideMesh ride $code.") { body, dialog ->\n                addPanelInfo(body, "Ride code", code, highlight = true)\n                val image = ImageView(this).apply {\n                    setImageBitmap(bitmap)\n                    adjustViewBounds = true\n                    setPadding(dp(12), dp(12), dp(12), dp(12))\n                    background = panelCardBackground()\n                }\n                body.addView(image, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {\n                    topMargin = dp(6)\n                    bottomMargin = dp(8)\n                })\n                addPanelButton(body, "SHARE QR") {\n                    dialog.dismiss()\n                    shareRideQr()\n                }\n            }\n        } catch (t: Throwable) {\n            log("Could not create QR: ${t.message ?: t.javaClass.simpleName}")\n        }\n    }\n\n    private fun shareRideQr''',
    'themed QR page',
)

# Riders page. Use public display names only.
s = sub_once(
    s,
    r'''    private fun showRidersDialog\(\) \{.*?    \}\n\n    private fun showAudioRouteDialog''',
    '''    private fun showRidersDialog() {\n        val me = binding.riderName.text?.toString().orEmpty().ifBlank { "Rider" }\n        val peers = if (internetNode.isConnected()) internetNode.remotePeers() else emptyList()\n        val total = peers.size + 1\n\n        showRideMeshPanel("RIDERS", "$total rider${if (total == 1) "" else "s"} currently visible in this ride.") { body, dialog ->\n            addPanelSection(body, "You")\n            addPanelInfo(body, me, "YOU • ${deviceLabel()}", highlight = true)\n\n            addPanelSection(body, "Connected riders")\n            if (peers.isEmpty()) {\n                addPanelInfo(body, "Waiting", "Another rider will appear here as soon as they join.")\n            } else {\n                peers.forEach { peer ->\n                    val quality = when (peer.qualityBars.coerceIn(1, 4)) {\n                        4 -> "Excellent"\n                        3 -> "Good"\n                        2 -> "Fair"\n                        else -> "Weak"\n                    }\n                    addPanelInfo(\n                        body,\n                        peer.displayName.ifBlank { "Rider" },\n                        "${peer.deviceName.ifBlank { "Android device" }} • $quality",\n                    )\n                }\n            }\n\n            addPanelButton(body, "INVITE RIDERS") {\n                dialog.dismiss()\n                showLiveInviteOptions()\n            }\n        }\n    }\n\n    private fun showAudioRouteDialog''',
    'themed riders page',
)

# Audio page.
s = sub_once(
    s,
    r'''    private fun showAudioRouteDialog\(\) \{.*?    \}\n\n    private fun transportModeLabel''',
    '''    private fun showAudioRouteDialog() {\n        val current = when (binding.audioRoute.checkedRadioButtonId) {\n            R.id.routePhone -> "Phone"\n            R.id.routeHelmet -> "Helmet / headset"\n            else -> "Automatic"\n        }\n        showRideMeshPanel("AUDIO", "Choose where RideMesh voice should play. Automatic is recommended while riding.") { body, dialog ->\n            addPanelInfo(body, "Current route", current, highlight = true)\n            addPanelInfo(body, "Voice", if (micMuted) "Microphone muted • listening only" else "Microphone active")\n\n            addPanelSection(body, "Audio route")\n            addPanelButton(body, if (current == "Automatic") "✓  AUTOMATIC" else "AUTOMATIC") {\n                binding.routeAuto.isChecked = true\n                applySelectedAudioRoute()\n                saveSettings()\n                dialog.dismiss()\n            }\n            addPanelButton(body, if (current == "Phone") "✓  PHONE" else "PHONE", primary = false) {\n                binding.routePhone.isChecked = true\n                applySelectedAudioRoute()\n                saveSettings()\n                dialog.dismiss()\n            }\n            addPanelButton(body, if (current == "Helmet / headset") "✓  HELMET / HEADSET" else "HELMET / HEADSET", primary = false) {\n                binding.routeHelmet.isChecked = true\n                applySelectedAudioRoute()\n                saveSettings()\n                dialog.dismiss()\n            }\n        }\n    }\n\n    private fun transportModeLabel''',
    'themed audio page',
)

# Settings page.
s = sub_once(
    s,
    r'''    private fun showSettingsAndHelpDialog\(\) \{.*?    \}\n\n    private fun ensureBetaFirstLaunch''',
    '''    private fun showSettingsAndHelpDialog() {\n        val email = savedUserEmail().ifBlank { "Not set" }\n        val rider = binding.riderName.text?.toString().orEmpty().ifBlank { riderNameFromEmail(email) }\n        showRideMeshPanel("SETTINGS", "RideMesh profile, support and ride preferences.") { body, dialog ->\n            addPanelSection(body, "Rider profile")\n            addPanelInfo(body, "Rider name", rider, highlight = true)\n            addPanelInfo(body, "Email", email)\n            addPanelButton(body, "EDIT RIDER NAME") {\n                dialog.dismiss()\n                showRiderNameEditor()\n            }\n            addPanelButton(body, "CHANGE EMAIL", primary = false) {\n                dialog.dismiss()\n                showEmailProfileScreen()\n            }\n\n            addPanelSection(body, "Beta")\n            addPanelInfo(body, "Access", betaStatusSentence())\n\n            addPanelSection(body, "Support")\n            addPanelButton(body, "WHATSAPP GROUP") {\n                dialog.dismiss()\n                openWhatsAppBugReport()\n            }\n            if (rideStarted) {\n                addPanelButton(body, "RIDE STATUS", primary = false) {\n                    dialog.dismiss()\n                    showRideStatusDialog()\n                }\n            }\n        }\n    }\n\n    private fun ensureBetaFirstLaunch''',
    'themed settings page',
)

# Status page. No implementation terms.
s = sub_once(
    s,
    r'''    private fun showRideStatusDialog\(\) \{.*?    \}\n\n    private fun openWhatsAppBugReport''',
    '''    private fun showRideStatusDialog() {\n        val diag = internetNode.diagnostics()\n        val connection = when {\n            diag.voicePeersConnected > 0 -> "Connected"\n            diag.signalingConnected -> "Ready"\n            else -> "Reconnecting…"\n        }\n        val voice = when {\n            micMuted -> "Muted"\n            diag.voicePeersConnected > 0 -> "Connected"\n            else -> "Ready"\n        }\n        val quality = when {\n            diag.voicePeersConnected > 0 -> "Good"\n            diag.signalingConnected -> "Ready"\n            else -> "Checking"\n        }\n        val riders = (diag.knownRiders + 1).coerceAtLeast(1)\n\n        showRideMeshPanel("RIDE STATUS", "Live rider-facing connection information.") { body, dialog ->\n            addPanelInfo(body, "Connection", connection, highlight = connection == "Connected")\n            addPanelInfo(body, "Voice", voice)\n            addPanelInfo(body, "Riders", "$riders connected")\n            addPanelInfo(body, "Microphone", if (micMuted) "Muted • listening only" else "Active")\n            addPanelInfo(body, "Voice quality", quality)\n            addPanelInfo(body, "Beta access", betaStatusSentence())\n            addPanelButton(body, "WHATSAPP SUPPORT") {\n                dialog.dismiss()\n                openWhatsAppBugReport()\n            }\n        }\n    }\n\n    private fun openWhatsAppBugReport''',
    'themed status page',
)

p.write_text(s)
print('Beta4.5 themed UI patch applied')
