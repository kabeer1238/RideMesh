package com.bikemesh.ridemesh

import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/** Brand reveal only. A ride still begins through the existing user initiated flow. */
class SplashActivity : AppCompatActivity() {
    private val handler = Handler(Looper.getMainLooper())
    private val enterApp = Runnable {
        if (!isFinishing) {
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }
    }
    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK); fitsSystemWindows = true }
        root.addView(ImageView(this).apply {
            setImageResource(R.drawable.rm_road)
            scaleType = ImageView.ScaleType.CENTER_CROP
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO
        }, FrameLayout.LayoutParams(-1, -1))
        root.addView(View(this).apply {
            background = GradientDrawable(GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(0x38000000, 0x00000000, 0xEA000607.toInt()))
        }, FrameLayout.LayoutParams(-1, -1))
        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(28), 0, dp(28), dp(28))
        }
        content.addView(View(this), LinearLayout.LayoutParams(1, 0, 0.28f))
        content.addView(ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_logo_exact)
            scaleType = ImageView.ScaleType.FIT_CENTER
            contentDescription = "RideMesh by Autopilot India"
        }, LinearLayout.LayoutParams(-1, dp(96)))
        content.addView(TextView(this).apply {
            text = "RIDE TOGETHER\nSTAY CONNECTED"
            textSize = 15f; letterSpacing = 0.25f
            gravity = Gravity.CENTER; setLineSpacing(dp(9).toFloat(), 1f)
            setTextColor(Color.WHITE)
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(20) })
        content.addView(View(this), LinearLayout.LayoutParams(1, 0, 0.72f))
        val info = packageManager.getPackageInfo(packageName, 0)
        content.addView(TextView(this).apply {
            text = "v${info.versionName}"
            textSize = 12f; setTextColor(Color.WHITE); gravity = Gravity.CENTER
            setTypeface(Typeface.DEFAULT, Typeface.BOLD)
        })
        content.addView(TextView(this).apply {
            text = "BY AUTOPILOTINDIA"; textSize = 9f; letterSpacing = 0.16f
            setTextColor(Color.parseColor("#AAC0C7")); gravity = Gravity.CENTER
        }, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(8) })
        content.addView(View(this).apply {
            background = GradientDrawable().apply {
                cornerRadius = dp(2).toFloat(); setColor(Color.parseColor("#00DEEB"))
            }
        }, LinearLayout.LayoutParams(dp(112), dp(3)).apply { topMargin = dp(18) })
        root.addView(content, FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        handler.postDelayed(enterApp, 1100L)
    }
    override fun onPause() {
        handler.removeCallbacks(enterApp)
        super.onPause()
    }
}
