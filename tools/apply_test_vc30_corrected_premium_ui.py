from pathlib import Path
import re

# vc30 TEST corrected premium UI.
# Clean base: vc28 / vc26 Active Ride UI. vc29 is deliberately NOT used.
# Goals:
# 1) Real photographic helmet/rider image on the upper-right of Active Ride, heavily faded into black.
# 2) Full-screen cinematic mountain-road splash with RideMesh logo/tagline/version/progress.
# 3) Proper full-face helmet silhouette inside rider avatar rings instead of letter initials.
# 4) Preserve vc28 no-billing test behavior and vc26 8-rider audio tuning.

# ---- Version ---------------------------------------------------------------
gradle = Path("app/build.gradle.kts")
s = gradle.read_text()
if 'versionCode = 28' not in s or 'versionName = "1.0.1-test28"' not in s:
    raise SystemExit('vc30 expected clean vc28 TEST identity before UI patch')
s = s.replace('versionCode = 28', 'versionCode = 30', 1)
s = s.replace('versionName = "1.0.1-test28"', 'versionName = "1.0.1-test30"', 1)
gradle.write_text(s)

# The workflow downloads these two photographic assets BEFORE this patch runs.
nodpi = Path('app/src/main/res/drawable-nodpi')
active_photo = nodpi / 'vc30_active_rider_photo.jpg'
splash_photo = nodpi / 'vc30_splash_road.jpg'
if not active_photo.exists() or active_photo.stat().st_size < 20000:
    raise SystemExit('vc30 rider photo asset missing/too small')
if not splash_photo.exists() or splash_photo.stat().st_size < 20000:
    raise SystemExit('vc30 splash road asset missing/too small')

# ---- Premium active background + helmet icon -------------------------------
drawable = Path('app/src/main/res/drawable')
drawable.mkdir(parents=True, exist_ok=True)

(drawable / 'vc30_active_photo_background.xml').write_text(r'''<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <!-- True black base. -->
    <item>
        <shape android:shape="rectangle">
            <solid android:color="#FF000000" />
        </shape>
    </item>

    <!-- Real rider/helmet photograph. The image is pre-cropped by the build workflow. -->
    <item android:gravity="top|end">
        <bitmap
            android:src="@drawable/vc30_active_rider_photo"
            android:gravity="top|end"
            android:filter="true"
            android:dither="true" />
    </item>

    <!-- Horizontal fade: keep all left-side title/status content extremely readable. -->
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="0"
                android:startColor="#FF000000"
                android:centerColor="#D6000000"
                android:endColor="#42000609" />
        </shape>
    </item>

    <!-- Vertical fade: photographic header disappears smoothly before cards/rider list. -->
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="270"
                android:startColor="#00000000"
                android:centerColor="#71000000"
                android:endColor="#FF000000" />
        </shape>
    </item>

    <!-- Very restrained RideMesh cyan atmosphere, not a graphic/icon. -->
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="0"
                android:startColor="#0000E8F5"
                android:centerColor="#0500E8F5"
                android:endColor="#1400E8F5" />
        </shape>
    </item>
</layer-list>
''')

(drawable / 'ic_vc30_rider_helmet.xml').write_text(r'''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="30dp"
    android:height="30dp"
    android:viewportWidth="64"
    android:viewportHeight="64">
    <!-- Premium full-face helmet outline rather than a filled cartoon blob. -->
    <path
        android:fillColor="#00000000"
        android:strokeColor="#13E7F3"
        android:strokeWidth="3.2"
        android:strokeLineJoin="round"
        android:strokeLineCap="round"
        android:pathData="M10,35 C10,18 21,9 36,9 C49,9 57,19 57,32 L57,40 C57,43 55,45 52,45 L48,45 C46,52 40,56 32,57 L23,57 C18,57 14,53 14,48 L14,43 L11,43 C10,43 10,39 10,35 Z" />
    <path
        android:fillColor="#071317"
        android:strokeColor="#EAFDFF"
        android:strokeWidth="2.5"
        android:strokeLineJoin="round"
        android:pathData="M21,25 C30,20 42,20 51,25 L48,34 L24,34 Z" />
    <path
        android:fillColor="#13E7F3"
        android:pathData="M25,39 L48,39 L46,43 L27,43 Z" />
    <path
        android:fillColor="#00000000"
        android:strokeColor="#13E7F3"
        android:strokeWidth="2.1"
        android:strokeLineCap="round"
        android:pathData="M17,18 C22,13 28,11 36,11" />
</vector>
''')

# ---- Active screen: set photographic layered background --------------------
layout_path = Path('app/src/main/res/layout/activity_main.xml')
xml = layout_path.read_text()

screen_pat = re.compile(
    r'(<[A-Za-z0-9_.]+(?=[^>]*android:id="@\+id/screenActive")[^>]*)(>)',
    re.S,
)
m = screen_pat.search(xml)
if not m:
    raise SystemExit('vc30 could not find screenActive opening tag')
tag = m.group(1)
if 'android:background=' in tag:
    tag = re.sub(r'android:background="[^"]*"', 'android:background="@drawable/vc30_active_photo_background"', tag, count=1)
else:
    tag += '\n        android:background="@drawable/vc30_active_photo_background"'
xml = xml[:m.start()] + tag + m.group(2) + xml[m.end():]
layout_path.write_text(xml)

# ---- MainActivity: helmet avatars -----------------------------------------
main = Path('app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt')
kt = main.read_text()

oncreate_anchor = '        setContentView(binding.root)\n'
if oncreate_anchor not in kt:
    raise SystemExit('vc30 setContentView anchor missing')
if 'VC30_HELMET_AVATAR_OBSERVER' not in kt:
    kt = kt.replace(
        oncreate_anchor,
        oncreate_anchor + '''        // VC30_HELMET_AVATAR_OBSERVER\n        // Preserve the approved rider cards; only replace one-letter avatar glyphs\n        // with the full-face RideMesh helmet silhouette.\n        binding.screenActive.viewTreeObserver.addOnGlobalLayoutListener {\n            applyVc30HelmetAvatars(binding.screenActive)\n        }\n''',
        1,
    )

helper = r'''    private fun applyVc30HelmetAvatars(root: View) {
        // VC30_HELMET_AVATAR_STYLE
        if (root is TextView) {
            val label = root.text?.toString()?.trim().orEmpty()
            val d = resources.displayMetrics.density
            val minAvatar = (34f * d).toInt()
            val maxAvatar = (90f * d).toInt()
            val looksLikeAvatar =
                label.length == 1 &&
                label[0].isLetter() &&
                root.background != null &&
                root.width in minAvatar..maxAvatar &&
                root.height in minAvatar..maxAvatar

            if (looksLikeAvatar) {
                root.setTextColor(Color.TRANSPARENT)
                val helmet = ContextCompat.getDrawable(this, R.drawable.ic_vc30_rider_helmet)?.mutate()
                val iconSize = (30f * d).toInt()
                helmet?.setBounds(0, 0, iconSize, iconSize)
                root.setCompoundDrawables(null, helmet, null, null)
                root.compoundDrawablePadding = 0
                root.gravity = Gravity.CENTER
            }
        }
        if (root is ViewGroup) {
            for (i in 0 until root.childCount) {
                applyVc30HelmetAvatars(root.getChildAt(i))
            }
        }
    }

'''
if 'VC30_HELMET_AVATAR_STYLE' not in kt:
    marker = '    private fun showSettingsAndHelpDialog()'
    idx = kt.find(marker)
    if idx < 0:
        raise SystemExit('vc30 helmet helper insertion anchor missing')
    kt = kt[:idx] + helper + kt[idx:]

main.write_text(kt)

# ---- Splash: photographic road + logo + tagline + progress ----------------
splash = Path('app/src/main/java/com/bikemesh/ridemesh/SplashActivity.kt')
splash.write_text(r'''package com.bikemesh.ridemesh

import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.Space
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/**
 * vc30 TEST cinematic boot screen.
 * No network, microphone, mesh or Billing work starts here.
 */
class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.BLACK
        @Suppress("DEPRECATION")
        run {
            window.decorView.systemUiVisibility =
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        }

        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }

        val road = ImageView(this).apply {
            setImageResource(R.drawable.vc30_splash_road)
            scaleType = ImageView.ScaleType.CENTER_CROP
        }
        root.addView(road, FrameLayout.LayoutParams(-1, -1))

        // Dark cinematic treatment keeps the scene photographic while matching RideMesh.
        val scrim = View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(
                    Color.argb(145, 0, 8, 12),
                    Color.argb(45, 0, 7, 10),
                    Color.argb(80, 0, 10, 14),
                    Color.argb(185, 0, 5, 8),
                ),
            )
        }
        root.addView(scrim, FrameLayout.LayoutParams(-1, -1))

        val cyanTint = View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.BOTTOM_TOP,
                intArrayOf(Color.argb(34, 0, 224, 240), Color.TRANSPARENT),
            )
        }
        root.addView(cyanTint, FrameLayout.LayoutParams(-1, -1))

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(28), dp(72), dp(28), dp(34))
        }
        root.addView(content, FrameLayout.LayoutParams(-1, -1))

        content.addView(Space(this), LinearLayout.LayoutParams(1, dp(64)))

        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_logo_exact)
            scaleType = ImageView.ScaleType.FIT_CENTER
            alpha = 0f
            translationY = dp(6).toFloat()
        }
        content.addView(logo, LinearLayout.LayoutParams(-1, dp(112)))

        val tagline = TextView(this).apply {
            text = "RIDE TOGETHER\nSTAY CONNECTED"
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(242, 248, 250))
            textSize = 15f
            typeface = Typeface.create("sans-serif", Typeface.NORMAL)
            letterSpacing = 0.26f
            setLineSpacing(0f, 1.28f)
            alpha = 0f
        }
        content.addView(tagline, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(18) })

        content.addView(Space(this), LinearLayout.LayoutParams(1, 0, 1f))

        val info = packageManager.getPackageInfo(packageName, 0)
        @Suppress("DEPRECATION")
        val build = if (android.os.Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()

        val version = TextView(this).apply {
            text = "v${info.versionName}  •  Build $build TEST"
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(221, 232, 238))
            textSize = 11f
            typeface = Typeface.create("sans-serif", Typeface.BOLD)
        }
        content.addView(version, LinearLayout.LayoutParams(-1, -2))

        val byline = TextView(this).apply {
            text = "BY AUTOPILOTINDIA"
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(165, 181, 190))
            textSize = 9f
            typeface = Typeface.create("sans-serif", Typeface.BOLD)
            letterSpacing = 0.16f
        }
        content.addView(byline, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })

        val track = FrameLayout(this).apply {
            background = rounded(Color.rgb(52, 67, 76), dp(2).toFloat())
        }
        content.addView(track, LinearLayout.LayoutParams(dp(220), dp(4)).apply { topMargin = dp(20) })

        val fill = View(this).apply {
            background = rounded(Color.rgb(17, 229, 243), dp(2).toFloat())
            pivotX = 0f
            scaleX = 0f
        }
        track.addView(fill, FrameLayout.LayoutParams(-1, -1))

        setContentView(root)

        logo.animate().alpha(1f).translationY(0f).setDuration(430L).start()
        tagline.animate().alpha(1f).setStartDelay(180L).setDuration(430L).start()
        fill.animate().scaleX(1f).setDuration(1200L).start()

        root.postDelayed({
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }, 1320L)
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun rounded(color: Int, radius: Float): GradientDrawable =
        GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            setColor(color)
            cornerRadius = radius
        }
}
''')

# ---- Safeguards ------------------------------------------------------------
checks = {
    'gradle': gradle.read_text(),
    'layout': layout_path.read_text(),
    'main': main.read_text(),
    'splash': splash.read_text(),
    'helmet': (drawable / 'ic_vc30_rider_helmet.xml').read_text(),
    'bg': (drawable / 'vc30_active_photo_background.xml').read_text(),
}
required = [
    ('gradle', 'versionCode = 30'),
    ('gradle', 'versionName = "1.0.1-test30"'),
    ('layout', '@drawable/vc30_active_photo_background'),
    ('layout', 'RIDE ACTIVE'),
    ('layout', 'HANDS-FREE INTERCOM'),
    ('main', 'VC30_HELMET_AVATAR_OBSERVER'),
    ('main', 'VC30_HELMET_AVATAR_STYLE'),
    ('main', 'VC28_TEST_NO_BILLING_GATE'),
    ('main', 'VC28_TEST_NO_BILLING_PAYWALL_DISABLED'),
    ('splash', 'RIDE TOGETHER'),
    ('splash', 'STAY CONNECTED'),
    ('splash', 'vc30_splash_road'),
    ('bg', 'vc30_active_rider_photo'),
]
for bucket, token in required:
    if token not in checks[bucket]:
        raise SystemExit(f'vc30 validation failed: {token} missing from {bucket}')

# Explicitly reject the failed vc29 flat-vector background strategy.
for forbidden in ['vc29_helmet_rider_silhouette', 'vc29_active_screen_bg', 'VC29_HELMET_AVATAR_STYLE']:
    if forbidden in checks['layout'] or forbidden in checks['main'] or forbidden in checks['bg']:
        raise SystemExit(f'vc30 must not include rejected vc29 visual: {forbidden}')

print('Applied vc30 TEST corrected premium UI from clean vc28 base')
