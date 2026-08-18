package com.bikemesh.ridemesh

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.widget.ImageView
import androidx.appcompat.app.AppCompatActivity

/**
 * Short, intentionally subtle brand reveal using the approved RideMesh artwork.
 * No network, radio or microphone work starts here; the real RideMesh session
 * remains entirely user initiated.
 */
class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = android.widget.FrameLayout(this).apply {
            setBackgroundColor(Color.BLACK)
        }
        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_boot_exact)
            scaleType = ImageView.ScaleType.FIT_CENTER
            alpha = 0f
            scaleX = 0.975f
            scaleY = 0.975f
        }

        root.addView(
            logo,
            android.widget.FrameLayout.LayoutParams(
                android.widget.FrameLayout.LayoutParams.MATCH_PARENT,
                android.widget.FrameLayout.LayoutParams.MATCH_PARENT,
            )
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
        private const val LOGO_REVEAL_MS = 420L
        private const val HOLD_MS = 140L
    }
}
