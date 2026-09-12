package com.bikemesh.ridemesh

import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.bikemesh.ridemesh.databinding.ActivityMainBinding
import com.google.android.material.button.MaterialButton

/** Debug-only sample data. Never included in a production release. */
class DesignPreviewActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var riders: LinearLayout
    private val cyan = Color.rgb(0, 222, 235)
    private var muted = false
    private fun dp(n: Int) = (n * resources.displayMetrics.density).toInt()
    private fun label(value: String, size: Float = 13f, color: Int = Color.WHITE) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color)
    }
    private fun button(value: String, action: () -> Unit) = MaterialButton(this).apply {
        text = value; textSize = 11f; minWidth = 0; cornerRadius = dp(14)
        setTextColor(cyan); backgroundTintList = ColorStateList.valueOf(Color.rgb(3, 30, 36))
        setOnClickListener { action() }
    }
    private fun message(title: String, body: String) {
        AlertDialog.Builder(this).setTitle(title).setMessage(body).setPositiveButton("OK", null).show()
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        binding.screenHome.visibility = View.GONE
        binding.screenActive.visibility = View.VISIBLE
        binding.riderCount.text = android.text.SpannableString("RIDE ACTIVE").apply {
            setSpan(android.text.style.ForegroundColorSpan(cyan), 5, 11, 0)
        }
        binding.meshStatus.text = "●  DESIGN PREVIEW • SAMPLE RIDERS"
        binding.activeRideCode.text = "RM2215"
        binding.activeVersion.text = "DESIGN PREVIEW • NO LIVE AUDIO"
        binding.activeMute.setOnClickListener {
            muted = !muted; binding.activeMute.text = if (muted) "MIC MUTED" else "MUTE MIC"
        }
        binding.activeStop.setOnClickListener { message("End ride", "In the live app this opens the existing end-ride confirmation. No voice session is running in this preview.") }
        binding.activeInvite.setOnClickListener { invite() }
        binding.activeAudio.setOnClickListener { message("Audio", "Preview of the audio control. The live app retains Automatic, Phone and Helmet / headset routes.") }
        binding.activeStatus.setOnClickListener { message("Ride status", "This preview uses sample riders. Live connection quality and rider state are supplied by the existing transport in the app.") }
        binding.activeTopSettings.setOnClickListener { openSettings() }
        listOf("Sulfekkar", "Fahad", "Shameer").forEachIndexed { i, name ->
            binding.riderGrid.addView(row(name, if (i == 0) "LIVE • YOU" else "LIVE • CONNECTED", true), GridLayout.LayoutParams().apply {
                rowSpec = GridLayout.spec(i); columnSpec = GridLayout.spec(0, 1f)
                width = 0; height = dp(72); setMargins(0, dp(4), 0, dp(4))
            })
        }
        riders = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(4))
            setBackgroundColor(Color.rgb(2, 8, 9)); visibility = View.GONE
        }
        riders.addView(label("RIDERS", 24f).apply { setTypeface(Typeface.DEFAULT, Typeface.BOLD) })
        riders.addView(label("8 RIDERS MAX • SAMPLE DATA", 10f, cyan))
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        listOf("Sulfekkar", "Fahad", "Shameer", "Niyas", "Rameez", "Jithin", "Vishnu", "Anees").forEachIndexed { i, name ->
            list.addView(row(name, when {i == 0 -> "LIVE • YOU"; i < 3 -> "LIVE • CONNECTED"; i < 5 -> "STANDBY"; else -> "OFFLINE"}, i < 3), LinearLayout.LayoutParams(-1, dp(76)))
        }
        riders.addView(ScrollView(this).apply { addView(list) }, LinearLayout.LayoutParams(-1, 0, 1f).apply { topMargin = dp(18) })
        riders.addView(button("+  INVITE RIDERS") { invite() }, LinearLayout.LayoutParams(-1, dp(58)))
        riders.addView(label("8 RIDERS MAX PER GROUP", 9f).apply { gravity = Gravity.CENTER }, LinearLayout.LayoutParams(-1, dp(28)))
        riders.addView(nav(true), LinearLayout.LayoutParams(-1, dp(74)))
        (binding.root as FrameLayout).addView(riders, FrameLayout.LayoutParams(-1, -1))
        binding.screenActive.addView(nav(false), LinearLayout.LayoutParams(-1, dp(74)))
    }
    private fun row(name: String, status: String, live: Boolean): View {
        val row = LinearLayout(this).apply {
            gravity = Gravity.CENTER_VERTICAL; setPadding(dp(10), dp(8), dp(10), dp(8))
            background = GradientDrawable().apply {
                cornerRadius = dp(14).toFloat(); setColor(Color.rgb(7, 12, 12)); setStroke(dp(1), Color.rgb(22, 50, 56))
            }
        }
        row.addView(ImageView(this).apply {
            setImageResource(R.drawable.rm_helmet_avatar); setPadding(dp(5), dp(5), dp(5), dp(5))
            contentDescription = "Rider helmet"
            background = GradientDrawable().apply { shape = GradientDrawable.OVAL; setColor(Color.rgb(3,18,23)); setStroke(dp(1), cyan) }
        }, LinearLayout.LayoutParams(dp(48), dp(48)))
        val text = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        text.addView(label(name, 14f).apply { setTypeface(Typeface.DEFAULT, Typeface.BOLD) })
        text.addView(label(status, 10f, if (live) cyan else Color.LTGRAY))
        row.addView(text, LinearLayout.LayoutParams(0, -2, 1f).apply { marginStart = dp(14) })
        if (live) row.addView(SignalBarsView(this, 4, Color.rgb(0,230,162)), LinearLayout.LayoutParams(dp(40), dp(36)))
        return row
    }
    private fun nav(onRiders: Boolean): View {
        val bar = LinearLayout(this)
        listOf("RIDE" to R.drawable.ic_rm_ride, "MAP" to R.drawable.ic_rm_map, "RIDERS" to R.drawable.ic_rm_riders, "SETTINGS" to R.drawable.ic_rm_settings).forEach { (name, icon) ->
            bar.addView(button(name) {
                when (name) {
                    "RIDE" -> { riders.visibility = View.GONE; binding.screenActive.visibility = View.VISIBLE }
                    "RIDERS" -> { riders.visibility = View.VISIBLE; binding.screenActive.visibility = View.GONE }
                    "MAP" -> message("Map", "The existing live group map remains in the app. This design preview does not request location or connect to a ride.")
                    else -> openSettings()
                }
            }.apply {
                setIconResource(icon); iconGravity = MaterialButton.ICON_GRAVITY_TOP; iconSize = dp(22); iconPadding = dp(2)
                iconTint = ColorStateList.valueOf(if ((name == "RIDERS") == onRiders && (name == "RIDE" || name == "RIDERS")) cyan else Color.LTGRAY)
                setPadding(dp(2), dp(4), dp(2), dp(4)); textSize = 9f
                backgroundTintList = ColorStateList.valueOf(if ((name == "RIDERS" && onRiders) || (name == "RIDE" && !onRiders)) Color.rgb(0,49,56) else Color.rgb(5,10,10))
            }, LinearLayout.LayoutParams(0, -1, 1f))
        }
        return bar
    }
    private fun invite() = message("Invite riders", "Sample ride code: RM2215. In the live app this opens the existing share and QR invitation controls.")
    private fun openSettings() {
        AlertDialog.Builder(this).setTitle("Design preview")
            .setMessage("Sample riders let you inspect the new interface. No audio or location session is running. Open the app to inspect the real profile, ride setup and subscription flows.")
            .setPositiveButton("OPEN APP") { _, _ -> startActivity(Intent(this, SplashActivity::class.java)) }
            .setNegativeButton("CLOSE", null).show()
    }
}
