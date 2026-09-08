from pathlib import Path

# Beta5.5.1 / vc25 — official RideMesh logo lock.
# Uses the exact existing official raster artwork and removes only its black
# rectangular background at runtime. No logo redrawing, font substitution,
# stretching, or geometry reinterpretation.

p = Path("app/build.gradle.kts")
s = p.read_text()
s = s.replace("versionCode = 24", "versionCode = 25")
s = s.replace(
    'versionName = "1.0.0-beta5.5-subscription-paywall"',
    'versionName = "1.0.0-beta5.5.1-official-logo-lock"',
)
p.write_text(s)

# Give the two exact RideMesh logo ImageViews stable IDs so the activity can
# install the transparency-cleaned bitmap without touching the artwork itself.
p = Path("app/src/main/res/layout/activity_main.xml")
s = p.read_text()
needle = '''                <ImageView
                    android:layout_width="218dp"
                    android:layout_height="76dp"'''
replacement = '''                <ImageView
                    android:id="@+id/homeRideMeshLogo"
                    android:layout_width="218dp"
                    android:layout_height="76dp"'''
if 'android:id="@+id/homeRideMeshLogo"' not in s:
    if needle not in s:
        raise SystemExit("home logo anchor not found")
    s = s.replace(needle, replacement, 1)

needle = '''        <ImageView
            android:layout_width="244dp"
            android:layout_height="72dp"'''
replacement = '''        <ImageView
            android:id="@+id/activeRideMeshLogo"
            android:layout_width="244dp"
            android:layout_height="72dp"'''
if 'android:id="@+id/activeRideMeshLogo"' not in s:
    if needle not in s:
        raise SystemExit("active logo anchor not found")
    s = s.replace(needle, replacement, 1)
p.write_text(s)

p = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = p.read_text()
if 'import android.graphics.BitmapFactory' not in s:
    s = s.replace('import android.graphics.Bitmap\n', 'import android.graphics.Bitmap\nimport android.graphics.BitmapFactory\n', 1)

call_anchor = '        setContentView(binding.root)\n'
if 'applyLockedOfficialRideMeshLogo()' not in s:
    if call_anchor not in s:
        raise SystemExit("setContentView anchor not found")
    s = s.replace(call_anchor, call_anchor + '        applyLockedOfficialRideMeshLogo()\n', 1)

if 'private fun applyLockedOfficialRideMeshLogo()' not in s:
    marker = '    private fun showScreen(screen: Screen) {'
    if marker not in s:
        raise SystemExit("showScreen anchor not found")
    helper = r'''    /**
     * Keeps the official RideMesh artwork pixel-for-pixel as supplied.
     * The source image was authored on black, so black backing pixels are
     * converted to alpha. Edge pixels are un-premultiplied from black to retain
     * the original white/cyan anti-aliasing instead of creating a dark halo.
     */
    private fun applyLockedOfficialRideMeshLogo() {
        val source = BitmapFactory.decodeResource(resources, R.drawable.ridemesh_logo_exact) ?: return
        val src = source.copy(Bitmap.Config.ARGB_8888, false)
        val width = src.width
        val height = src.height
        val pixels = IntArray(width * height)
        src.getPixels(pixels, 0, width, 0, 0, width, height)

        for (i in pixels.indices) {
            val color = pixels[i]
            val r = Color.red(color)
            val g = Color.green(color)
            val b = Color.blue(color)
            val alpha = maxOf(r, g, b)
            if (alpha <= 4) {
                pixels[i] = Color.TRANSPARENT
            } else {
                // Recover the source edge colour from its black composite.
                val rr = (r * 255 / alpha).coerceIn(0, 255)
                val gg = (g * 255 / alpha).coerceIn(0, 255)
                val bb = (b * 255 / alpha).coerceIn(0, 255)
                pixels[i] = Color.argb(alpha, rr, gg, bb)
            }
        }

        val transparent = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        transparent.setPixels(pixels, 0, width, 0, 0, width, height)
        binding.homeRideMeshLogo.setImageBitmap(transparent)
        binding.activeRideMeshLogo.setImageBitmap(transparent)
    }

'''
    s = s.replace(marker, helper + marker, 1)
p.write_text(s)
