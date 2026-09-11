from pathlib import Path
import re

# vc29 TEST visual refinement layer.
# Base: proven vc26 Active Ride UI + vc28 no-billing test bypass.
# Changes only the three approved visual areas:
#   1) subtle helmet/rider background on Active Ride screen
#   2) premium splash/boot presentation
#   3) helmet silhouette instead of letter initials in rider avatar circles

# ---- Version ---------------------------------------------------------------
gradle = Path("app/build.gradle.kts")
s = gradle.read_text()
if 'versionCode = 28' not in s or 'versionName = "1.0.1-test28"' not in s:
    raise SystemExit('vc29 expected vc28 test identity before refinement')
s = s.replace('versionCode = 28', 'versionCode = 29', 1)
s = s.replace('versionName = "1.0.1-test28"', 'versionName = "1.0.1-test29"', 1)
gradle.write_text(s)

# ---- Drawables -------------------------------------------------------------
drawable = Path("app/src/main/res/drawable")
drawable.mkdir(parents=True, exist_ok=True)

(drawable / "ic_vc29_rider_helmet.xml").write_text(r'''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="28dp"
    android:height="28dp"
    android:viewportWidth="100"
    android:viewportHeight="100">
    <path
        android:fillColor="#10E6F2"
        android:pathData="M14,54 C14,29 31,12 55,12 C77,12 92,28 92,49 L92,62 L81,62 C78,73 69,81 56,83 L39,83 C31,83 25,77 25,69 L25,62 L18,62 C16,62 14,59 14,54 Z" />
    <path
        android:fillColor="#071317"
        android:pathData="M31,38 C44,29 65,28 81,38 L76,50 L37,50 Z" />
    <path
        android:fillColor="#EAFDFF"
        android:pathData="M41,55 L77,55 L74,63 L42,63 Z" />
</vector>
''')

(drawable / "vc29_helmet_rider_silhouette.xml").write_text(r'''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="260dp"
    android:height="330dp"
    android:viewportWidth="260"
    android:viewportHeight="330">
    <path
        android:fillColor="#162D35"
        android:fillAlpha="0.78"
        android:pathData="M28,126 C28,61 76,20 140,20 C199,20 236,61 239,119 L239,161 L214,161 C206,190 184,211 151,218 L102,218 C57,212 28,176 28,137 Z" />
    <path
        android:fillColor="#0DDCEB"
        android:fillAlpha="0.20"
        android:pathData="M76,80 C113,55 172,54 218,83 L207,119 L94,119 Z" />
    <path
        android:fillColor="#020A0D"
        android:fillAlpha="0.88"
        android:pathData="M93,126 L217,126 L210,151 L106,151 Z" />
    <path
        android:fillColor="#173039"
        android:fillAlpha="0.64"
        android:pathData="M49,286 C68,246 104,220 145,220 C189,220 224,246 244,292 L244,330 L30,330 L30,310 Z" />
    <path
        android:fillColor="#10E6F2"
        android:fillAlpha="0.12"
        android:pathData="M218,44 C235,65 244,91 244,122 L244,170 C244,177 239,183 232,184 L223,184 L223,122 C223,92 218,66 206,46 Z" />
</vector>
''')

(drawable / "vc29_active_screen_bg.xml").write_text(r'''<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="0"
                android:startColor="#FF000000"
                android:centerColor="#FF010608"
                android:endColor="#FF031116" />
        </shape>
    </item>
    <item
        android:width="260dp"
        android:height="330dp"
        android:gravity="top|end"
        android:top="54dp"
        android:right="-14dp"
        android:drawable="@drawable/vc29_helmet_rider_silhouette" />
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="0"
                android:startColor="#1100E8F5"
                android:centerColor="#0500E8F5"
                android:endColor="#00000000" />
        </shape>
    </item>
</layer-list>
''')

# ---- Active screen background ---------------------------------------------
layout_path = Path("app/src/main/res/layout/activity_main.xml")
xml = layout_path.read_text()

screen_pat = re.compile(
    r'(<[A-Za-z0-9_.]+(?=[^>]*android:id="@\+id/screenActive")[^>]*)(>)',
    re.S,
)
m = screen_pat.search(xml)
if not m:
    raise SystemExit('vc29 could not find screenActive opening tag')
tag = m.group(1)
if 'android:background=' in tag:
    tag = re.sub(r'android:background="[^"]*"', 'android:background="@drawable/vc29_active_screen_bg"', tag, count=1)
else:
    tag += '\n        android:background="@drawable/vc29_active_screen_bg"'
xml = xml[:m.start()] + tag + m.group(2) + xml[m.end():]
layout_path.write_text(xml)

# ---- MainActivity: rider avatar helmet styling -----------------------------
main = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
kt = main.read_text()

oncreate_anchor = '        setContentView(binding.root)\n'
if oncreate_anchor not in kt:
    raise SystemExit('vc29 setContentView anchor missing')
if 'VC29_HELMET_AVATAR_OBSERVER' not in kt:
    kt = kt.replace(
        oncreate_anchor,
        oncreate_anchor + '''        // VC29_HELMET_AVATAR_OBSERVER\n        // Keep the proven rider-card layout, but render a motorcycle helmet\n        // silhouette inside the existing circular avatar rings instead of letters.\n        binding.screenActive.viewTreeObserver.addOnGlobalLayoutListener {\n            applyVc29HelmetAvatars(binding.screenActive)\n        }\n''',
        1,
    )

helper = r'''    private fun applyVc29HelmetAvatars(root: View) {
        // VC29_HELMET_AVATAR_STYLE
        if (root is TextView) {
            val label = root.text?.toString()?.trim().orEmpty()
            val d = resources.displayMetrics.density
            val minAvatar = (34f * d).toInt()
            val maxAvatar = (84f * d).toInt()
            val looksLikeAvatar =
                label.length == 1 &&
                label[0].isLetter() &&
                root.background != null &&
                root.width in minAvatar..maxAvatar &&
                root.height in minAvatar..maxAvatar

            if (looksLikeAvatar) {
                root.setTextColor(Color.TRANSPARENT)
                val helmet = ContextCompat.getDrawable(this, R.drawable.ic_vc29_rider_helmet)?.mutate()
                val iconSize = (27f * d).toInt()
                helmet?.setBounds(0, 0, iconSize, iconSize)
                root.setCompoundDrawables(null, helmet, null, null)
                root.compoundDrawablePadding = 0
                root.gravity = Gravity.CENTER
            }
        }
        if (root is ViewGroup) {
            for (i in 0 until root.childCount) {
                applyVc29HelmetAvatars(root.getChildAt(i))
            }
        }
    }

'''
if 'VC29_HELMET_AVATAR_STYLE' not in kt:
    marker = '    private fun showSettingsAndHelpDialog()'
    idx = kt.find(marker)
    if idx < 0:
        # fallback to first private function after showScreen area
        marker = '    private fun '
        idx = kt.find(marker, kt.find('override fun onCreate'))
    if idx < 0:
        raise SystemExit('vc29 helper insertion anchor missing')
    kt = kt[:idx] + helper + kt[idx:]

main.write_text(kt)

# ---- Premium splash / boot presentation ----------------------------------
splash = Path("app/src/main/java/com/bikemesh/ridemesh/SplashActivity.kt")
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

/** vc29 premium boot presentation. No network/audio work starts here. */
class SplashActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.statusBarColor = Color.TRANSPARENT
        window.navigationBarColor = Color.BLACK
        window.decorView.systemUiVisibility =
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN

        val root = FrameLayout(this).apply { setBackgroundColor(Color.BLACK) }

        val roadBackground = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_boot_exact)
            scaleType = ImageView.ScaleType.CENTER_CROP
            alpha = 0.72f
        }
        root.addView(roadBackground, FrameLayout.LayoutParams(-1, -1))

        val scrim = View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.TOP_BOTTOM,
                intArrayOf(
                    Color.argb(70, 0, 0, 0),
                    Color.argb(35, 0, 8, 11),
                    Color.argb(185, 0, 4, 7),
                ),
            )
        }
        root.addView(scrim, FrameLayout.LayoutParams(-1, -1))

        val content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(28), dp(72), dp(28), dp(34))
        }
        root.addView(content, FrameLayout.LayoutParams(-1, -1))

        content.addView(Space(this), LinearLayout.LayoutParams(1, dp(52)))

        val logo = ImageView(this).apply {
            setImageResource(R.drawable.ridemesh_logo_exact)
            scaleType = ImageView.ScaleType.FIT_CENTER
            alpha = 0f
            scaleX = 0.97f
            scaleY = 0.97f
        }
        content.addView(logo, LinearLayout.LayoutParams(-1, dp(112)))

        val tagline = TextView(this).apply {
            text = "RIDE TOGETHER\nSTAY CONNECTED"
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(240, 247, 250))
            textSize = 15f
            typeface = Typeface.create("sans-serif", Typeface.BOLD)
            letterSpacing = 0.24f
            setLineSpacing(0f, 1.25f)
        }
        content.addView(tagline, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(18) })

        content.addView(Space(this), LinearLayout.LayoutParams(1, 0, 1f))

        val info = packageManager.getPackageInfo(packageName, 0)
        @Suppress("DEPRECATION")
        val build = if (android.os.Build.VERSION.SDK_INT >= 28) info.longVersionCode else info.versionCode.toLong()
        val version = TextView(this).apply {
            text = "v${info.versionName}  •  Build $build TEST"
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(218, 230, 237))
            textSize = 11f
            typeface = Typeface.create("sans-serif", Typeface.BOLD)
        }
        content.addView(version, LinearLayout.LayoutParams(-1, -2))

        val byline = TextView(this).apply {
            text = "BY AUTOPILOTINDIA"
            gravity = Gravity.CENTER
            setTextColor(Color.rgb(157, 176, 186))
            textSize = 9f
            typeface = Typeface.create("sans-serif", Typeface.BOLD)
            letterSpacing = 0.16f
        }
        content.addView(byline, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(6) })

        val track = FrameLayout(this).apply {
            background = rounded(Color.rgb(47, 62, 70), dp(2).toFloat())
        }
        content.addView(track, LinearLayout.LayoutParams(dp(220), dp(4)).apply { topMargin = dp(20) })

        val fill = View(this).apply {
            background = rounded(Color.rgb(16, 230, 242), dp(2).toFloat())
            pivotX = 0f
            scaleX = 0f
        }
        track.addView(fill, FrameLayout.LayoutParams(-1, -1))

        setContentView(root)

        logo.animate().alpha(1f).scaleX(1f).scaleY(1f).setDuration(420L).start()
        fill.animate().scaleX(1f).setDuration(1150L).start()

        root.postDelayed({
            startActivity(Intent(this, MainActivity::class.java))
            finish()
        }, 1280L)
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
    'helmet': (drawable / 'ic_vc29_rider_helmet.xml').read_text(),
}
required = [
    ('gradle', 'versionCode = 29'),
    ('gradle', 'versionName = "1.0.1-test29"'),
    ('layout', '@drawable/vc29_active_screen_bg'),
    ('layout', 'RIDE ACTIVE'),
    ('layout', 'HANDS-FREE INTERCOM'),
    ('main', 'VC29_HELMET_AVATAR_OBSERVER'),
    ('main', 'VC29_HELMET_AVATAR_STYLE'),
    ('main', 'VC28_TEST_NO_BILLING_GATE'),
    ('splash', 'RIDE TOGETHER'),
    ('splash', 'STAY CONNECTED'),
    ('splash', 'ridemesh_boot_exact'),
    ('helmet', '#10E6F2'),
]
for bucket, token in required:
    if token not in checks[bucket]:
        raise SystemExit(f'vc29 validation failed: {token} missing from {bucket}')

print('Applied vc29 TEST refined visuals: helmet background, premium splash, helmet avatars')
