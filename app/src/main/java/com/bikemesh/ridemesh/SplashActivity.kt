package com.bikemesh.ridemesh

import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.FrameLayout
import android.widget.ImageView
import androidx.appcompat.app.AppCompatActivity

/**
 * Short, intentionally subtle brand reveal. No network, radio or microphone work
 * starts here; the real RideMesh session remains entirely user initiated.
 */
class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = FrameLayout(this).apply {
            setBackgroundColor(android.graphics.Color.BLACK)
        }
        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_logo)
            scaleType = ImageView.ScaleType.CENTER_INSIDE
            alpha = 0f
            scaleX = 0.965f
            scaleY = 0.965f
        }
        val size = (resources.displayMetrics.widthPixels * 0.54f).toInt()
        root.addView(logo, FrameLayout.LayoutParams(size, size, Gravity.CENTER))
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
        private const val LOGO_REVEAL_MS = 540L
        private const val HOLD_MS = 150L
    }
}
