package com.bikemesh.ridemesh

import android.content.Context
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.PorterDuff
import android.graphics.PorterDuffXfermode
import android.util.AttributeSet

/** Screen composition removes the black matte while preserving the supplied artwork. */
class BrandImageView @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null
) : androidx.appcompat.widget.AppCompatImageView(context, attrs) {
    private val brandPaint = Paint().apply {
        xfermode = PorterDuffXfermode(PorterDuff.Mode.SCREEN)
    }

    override fun onDraw(canvas: Canvas) {
        val saved = canvas.saveLayer(0f, 0f, width.toFloat(), height.toFloat(), brandPaint)
        super.onDraw(canvas)
        canvas.restoreToCount(saved)
    }
}
