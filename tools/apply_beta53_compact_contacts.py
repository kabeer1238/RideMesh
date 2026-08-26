from pathlib import Path
import re

def once(s, old, new, label):
    if new in s:
        return s
    if old not in s:
        raise SystemExit(f"{label}: anchor not found")
    return s.replace(old, new, 1)

# vc22 version
p = Path("app/build.gradle.kts")
s = p.read_text().replace("versionCode = 21", "versionCode = 22")
s = s.replace('versionName = "1.0.0-beta5.2.1-ios-rml1-location"', 'versionName = "1.0.0-beta5.3-compact-map-contacts"')
p.write_text(s)

# Optional phone on Create/Join setup screen
p = Path("app/src/main/res/layout/activity_main.xml")
s = p.read_text()
if '@+id/riderPhone' not in s:
    i = s.find('android:id="@+id/rideCode"')
    if i < 0: raise SystemExit("rideCode not found")
    j = s.find("/>", i)
    if j < 0: raise SystemExit("rideCode closing tag not found")
    j += 2
    s = s[:j] + r'''
                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="12dp"
                    android:text="PHONE NUMBER (OPTIONAL)"
                    android:textColor="@color/faint"
                    android:textSize="10sp"
                    android:textStyle="bold" />

                <EditText
                    android:id="@+id/riderPhone"
                    android:layout_width="match_parent"
                    android:layout_height="52dp"
                    android:backgroundTint="@color/accent"
                    android:hint="+91 98765 43210 • country code for WhatsApp"
                    android:inputType="phone"
                    android:maxLength="24"
                    android:textColor="@color/white"
                    android:textColorHint="@color/faint"
                    android:textSize="15sp" />
''' + s[j:]
p.write_text(s)

p = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = p.read_text()

if "binding.riderPhone.setText(prefs.getString(RIDER_PHONE_KEY" not in s:
    s = once(s, "        restoreSettings()\n",
        '        restoreSettings()\n        binding.riderPhone.setText(prefs.getString(RIDER_PHONE_KEY, "").orEmpty())\n',
        "restore phone")

old = '''        binding.riderName.setText(rider)
        binding.rideCode.setText(code)
        transportMode = TransportMode.INTERNET_ONLY
'''
new = '''        binding.riderName.setText(rider)
        binding.rideCode.setText(code)
        val ridePhone = normalizeRiderPhone(binding.riderPhone.text?.toString().orEmpty())
        binding.riderPhone.setText(ridePhone)
        prefs.edit().putString(RIDER_PHONE_KEY, ridePhone).apply()
        transportMode = TransportMode.INTERNET_ONLY
'''
if "val ridePhone = normalizeRiderPhone(binding.riderPhone" not in s:
    s = once(s, old, new, "save phone")

# Compact marker: 176x92 -> 132x58, two clean lines only
pat = re.compile(r'''    private fun createRiderMarkerBitmap\(.*?\n    private fun distanceMeters''', re.S)
compact = r'''    private fun createRiderMarkerBitmap(
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

    private fun distanceMeters'''
if "val width = dp(132)" not in s:
    s, n = pat.subn(compact, s, count=1)
    if n != 1: raise SystemExit(f"compact marker count={n}")

old = '''            actions.addView(mapActionButton("CALL") { openRiderDialer(location.phoneNumber) }, LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginStart = dp(5); marginEnd = dp(5) })
            actions.addView(mapActionButton("MESSAGE") { openRiderMessage(location.phoneNumber) }, LinearLayout.LayoutParams(0, dp(52), 1f))
'''
new = '''            actions.addView(mapActionButton("CALL") { showRiderCallOptions(location.phoneNumber) }, LinearLayout.LayoutParams(0, dp(52), 1f).apply { marginStart = dp(5); marginEnd = dp(5) })
            actions.addView(mapActionButton("MESSAGE") { showRiderMessageOptions(location.phoneNumber) }, LinearLayout.LayoutParams(0, dp(52), 1f))
'''
if "showRiderCallOptions(location.phoneNumber)" not in s:
    s = once(s, old, new, "contact buttons")

if "private fun showRiderCallOptions(phone: String)" not in s:
    anchor = "    private fun openRiderDialer(phone: String) {\n"
    helpers = r'''    private fun showRiderCallOptions(phone: String) {
        val safe = normalizeRiderPhone(phone)
        if (safe.isBlank()) {
            Toast.makeText(this, "This rider has not shared a phone number.", Toast.LENGTH_SHORT).show()
            return
        }
        showRideMeshPanel("CALL RIDER", safe) { body, dialog ->
            addPanelButton(body, "WHATSAPP CALL") { dialog.dismiss(); openWhatsAppCall(safe) }
            addPanelButton(body, "NORMAL CALL", primary = false) { dialog.dismiss(); openRiderDialer(safe) }
        }
    }

    private fun showRiderMessageOptions(phone: String) {
        val safe = normalizeRiderPhone(phone)
        if (safe.isBlank()) {
            Toast.makeText(this, "This rider has not shared a phone number.", Toast.LENGTH_SHORT).show()
            return
        }
        showRideMeshPanel("MESSAGE RIDER", safe) { body, dialog ->
            addPanelButton(body, "WHATSAPP MESSAGE") { dialog.dismiss(); openWhatsAppMessage(safe) }
            addPanelButton(body, "NORMAL MESSAGE", primary = false) { dialog.dismiss(); openRiderMessage(safe) }
        }
    }

    private fun whatsappDigits(phone: String) = normalizeRiderPhone(phone).filter { it.isDigit() }

    private fun openWhatsAppCall(phone: String) {
        val digits = whatsappDigits(phone)
        if (digits.isBlank()) return
        val uri = Uri.parse("whatsapp://call?number=$digits")
        for (pkg in listOf("com.whatsapp", "com.whatsapp.w4b")) {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, uri).apply { setPackage(pkg) })
                return
            } catch (_: ActivityNotFoundException) { }
        }
        openWhatsAppMessage(phone)
        Toast.makeText(this, "Direct WhatsApp call unavailable — opened chat; tap the call icon.", Toast.LENGTH_LONG).show()
    }

    private fun openWhatsAppMessage(phone: String) {
        val digits = whatsappDigits(phone)
        if (digits.isBlank()) return
        val uri = Uri.parse("https://wa.me/$digits")
        for (pkg in listOf("com.whatsapp", "com.whatsapp.w4b")) {
            try {
                startActivity(Intent(Intent.ACTION_VIEW, uri).apply { setPackage(pkg) })
                return
            } catch (_: ActivityNotFoundException) { }
        }
        try { startActivity(Intent(Intent.ACTION_VIEW, uri)) }
        catch (_: ActivityNotFoundException) {
            Toast.makeText(this, "WhatsApp is not available on this device.", Toast.LENGTH_SHORT).show()
        }
    }

'''
    s = once(s, anchor, helpers + anchor, "contact helpers")

p.write_text(s)
print("Beta5.3 vc22 compact map + optional phone + contact submenus applied")
