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

        val root = android.widget.FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
        }
        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_logo_exact)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            alpha = 0f
            scaleX = 0.97f
            scaleY = 0.97f
        }

        val width = (resources.displayMetrics.widthPixels * 0.76f).toInt()
        val height = (width * 189f / 342f).toInt()
        root.addView(
            logo,
            android.widget.FrameLayout.LayoutParams(width, height, Gravity.CENTER)
        )
        setContentView(root)

        logo.animate()
            .alpha(1f)
            .scaleX(1f)
            .scaleY(1f)
            .setDuration(LOGO_REVEAL_MS)
            .withEndAction {
                logo.postDelayed({
                    startActivity(Intent(this, MainActivity::class.java))
                    finish()
                }, HOLD_MS)
            }
            .start()
    }

    companion object {
        private const val LOGO_REVEAL_MS = 440L
        private const val HOLD_MS = 120L
    }
}
