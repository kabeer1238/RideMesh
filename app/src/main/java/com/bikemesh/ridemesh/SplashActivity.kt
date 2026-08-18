package com.bikemesh.ridemesh

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.view.Gravity
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * Short, intentionally subtle brand reveal. No network, radio or microphone work
 * starts here; the real RideMesh session remains entirely user initiated.
 */
class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val density = resources.displayMetrics.density
        fun dp(value: Int) = (value * density).toInt()

        val brand = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(Color.BLACK)
            alpha = 0f
            scaleX = 0.97f
            scaleY = 0.97f
        }

        val mark = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_brand_mark)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
        }
        brand.addView(mark, LinearLayout.LayoutParams(dp(132), dp(108)))

        val name = TextView(this).apply {
            text = "RIDE MESH"
            setTextColor(Color.WHITE)
            textSize = 26f
            letterSpacing = 0.12f
            gravity = Gravity.CENTER
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        brand.addView(name, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT))

        val byline = TextView(this).apply {
            text = "BY AUTOPILOT INDIA  •  BETA 1.1"
            setTextColor(Color.rgb(0, 230, 230))
            textSize = 10f
            letterSpacing = 0.05f
            gravity = Gravity.CENTER
        }
        brand.addView(byline, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(5)
        })

        setContentView(brand)

        brand.animate()
            .alpha(1f)
            .scaleX(1f)
            .scaleY(1f)
            .setDuration(LOGO_REVEAL_MS)
            .withEndAction {
                brand.postDelayed({
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                }, HOLD_MS)
            }
            .start()
    }

    companion object {
        private const val LOGO_REVEAL_MS = 480L
        private const val HOLD_MS = 140L
    }
}
