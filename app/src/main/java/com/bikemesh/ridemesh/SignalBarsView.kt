package com.bikemesh.ridemesh

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.View

/** Connection quality from the transport, expressed as four readable bars. */
class SignalBarsView(context: Context, private val bars: Int, private val tint: Int) : View(context) {
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    init { contentDescription = "Signal quality ${bars.coerceIn(0, 4)} of 4" }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val unit = resources.displayMetrics.density
        val left = (width - 26 * unit) / 2f
        val bottom = (height + 24 * unit) / 2f
        repeat(4) { index ->
            paint.color = if (index < bars) tint else Color.parseColor("#244047")
            val x = left + index * 7 * unit
            canvas.drawRoundRect(x, bottom - (9 + index * 5) * unit, x + 4 * unit, bottom, unit, unit, paint)
        }
    }
}
