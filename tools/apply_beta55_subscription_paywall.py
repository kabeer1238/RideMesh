from pathlib import Path

# Beta5.5 / vc24 — Google Play Billing subscription gate.
# The 7-day free trial and regional prices are configured in Play Console.
# RideMesh always renders the localized price returned by Google Play.

p = Path("app/build.gradle.kts")
s = p.read_text()
s = s.replace("versionCode = 23", "versionCode = 24")
s = s.replace(
    'versionName = "1.0.0-beta5.4-cluster-bottomsheet"',
    'versionName = "1.0.0-beta5.5-subscription-paywall"',
)
if 'com.android.billingclient:billing-ktx' not in s:
    s = s.replace(
        '    implementation("com.google.android.material:material:1.12.0")\n',
        '    implementation("com.google.android.material:material:1.12.0")\n    implementation("com.android.billingclient:billing-ktx:7.1.1")\n',
    )
p.write_text(s)

p = Path("app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt")
s = p.read_text()

if 'com.bikemesh.ridemesh.billing.RideMeshBillingManager' not in s:
    s = s.replace(
        'import com.bikemesh.ridemesh.beta.BetaWindow\n',
        'import com.bikemesh.ridemesh.beta.BetaWindow\nimport com.bikemesh.ridemesh.billing.RideMeshBillingManager\n',
    )

if 'private lateinit var billingManager: RideMeshBillingManager' not in s:
    s = s.replace(
        '    private lateinit var audioEngine: AudioEngine\n',
        '    private lateinit var audioEngine: AudioEngine\n    private lateinit var billingManager: RideMeshBillingManager\n    private var billingProduct: RideMeshBillingManager.SubscriptionDisplay? = null\n    private var premiumPaywallDialog: android.app.Dialog? = null\n',
    )

billing_init = '''\n        billingManager = RideMeshBillingManager(\n            context = this,\n            onEntitlementChanged = { active ->\n                runOnUiThread {\n                    if (active) {\n                        premiumPaywallDialog?.dismiss()\n                        premiumPaywallDialog = null\n                    }\n                }\n            },\n            onProductChanged = { product ->\n                runOnUiThread {\n                    billingProduct = product\n                    if (premiumPaywallDialog?.isShowing == true) {\n                        premiumPaywallDialog?.dismiss()\n                        premiumPaywallDialog = null\n                        showPremiumPaywall()\n                    }\n                }\n            },\n            onBillingMessage = { message ->\n                runOnUiThread { android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show() }\n            },\n        )\n        billingManager.start()\n'''
if 'billingManager = RideMeshBillingManager(' not in s:
    anchor = '        applyPowerUi()\n'
    if anchor not in s:
        raise SystemExit('onCreate billing init anchor not found')
    s = s.replace(anchor, anchor + billing_init, 1)

s = s.replace(
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            binding.setupTitle.text = "CREATE RIDE"',
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            if (!ensurePremiumAccess()) return@setOnClickListener\n            binding.setupTitle.text = "CREATE RIDE"',
    1,
)
s = s.replace(
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            binding.setupTitle.text = "JOIN RIDE"',
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            if (!ensurePremiumAccess()) return@setOnClickListener\n            binding.setupTitle.text = "JOIN RIDE"',
    1,
)

if 'private fun ensurePremiumAccess()' not in s:
    marker = '    private fun showSettingsAndHelpDialog()'
    idx = s.find(marker)
    if idx < 0:
        raise SystemExit('settings method anchor not found')
    block = r'''    private fun ensurePremiumAccess(): Boolean {
        if (::billingManager.isInitialized && billingManager.hasPremiumEntitlement) return true
        showPremiumPaywall()
        return false
    }

    private fun showPremiumPaywall() {
        if (isFinishing || isDestroyed) return
        premiumPaywallDialog?.dismiss()

        val product = billingProduct
        val pad = (20 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
            background = GradientDrawable().apply {
                setColor(Color.rgb(10, 15, 18))
                cornerRadius = 24f * resources.displayMetrics.density
                setStroke((1 * resources.displayMetrics.density).toInt(), Color.rgb(0, 224, 255))
            }
        }

        root.addView(TextView(this).apply {
            text = "RIDEMESH PREMIUM"
            textSize = 23f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
        })
        root.addView(TextView(this).apply {
            text = if (product?.hasSevenDayTrial == true) "7 DAYS FREE" else "RIDEMESH PREMIUM"
            textSize = 19f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.rgb(0, 229, 255))
            gravity = Gravity.CENTER
            setPadding(0, dp(14), 0, dp(6))
        })
        root.addView(TextView(this).apply {
            text = "Ride together. Stay connected.\n\nHands-free group voice • Live Rider Map • rider speed and distance • call, message and navigate actions."
            textSize = 14f
            setTextColor(Color.rgb(220, 228, 232))
            gravity = Gravity.CENTER
            setLineSpacing(0f, 1.12f)
        })

        val priceText = when {
            product == null -> "Connecting to Google Play for your local price…"
            product.hasSevenDayTrial -> "Free for 7 days\nThen ${product.localizedMonthlyPrice} / month"
            else -> "${product.localizedMonthlyPrice} / month"
        }
        root.addView(TextView(this).apply {
            text = priceText
            textSize = 18f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(Color.WHITE)
            gravity = Gravity.CENTER
            setPadding(0, dp(18), 0, dp(6))
        })
        root.addView(TextView(this).apply {
            text = "Your exact local price is provided by Google Play before purchase. Subscription renews monthly unless cancelled. Cancel anytime in Google Play."
            textSize = 11.5f
            setTextColor(Color.rgb(155, 169, 177))
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, dp(14))
        })

        root.addView(MaterialButton(this).apply {
            text = if (product?.hasSevenDayTrial == true) "START 7-DAY FREE TRIAL" else if (product != null) "CONTINUE" else "RETRY PRICE"
            isAllCaps = true
            setTextColor(Color.BLACK)
            backgroundTintList = ColorStateList.valueOf(Color.rgb(0, 229, 255))
            setOnClickListener {
                if (product == null) {
                    billingManager.refresh()
                } else {
                    billingManager.launchPurchase(this@MainActivity)
                }
            }
        })
        root.addView(MaterialButton(this).apply {
            text = "RESTORE PURCHASE"
            setTextColor(Color.WHITE)
            backgroundTintList = ColorStateList.valueOf(Color.rgb(28, 35, 40))
            setOnClickListener { billingManager.restorePurchases() }
        })
        root.addView(TextView(this).apply {
            text = "Privacy Policy   •   Terms"
            textSize = 12f
            setTextColor(Color.rgb(0, 229, 255))
            gravity = Gravity.CENTER
            setPadding(0, dp(10), 0, 0)
            setOnClickListener {
                runCatching {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://autopilotindia.com/ridemesh-privacy-policy/")))
                }
            }
        })

        premiumPaywallDialog = android.app.Dialog(this).apply {
            setContentView(root)
            setCancelable(true)
            window?.apply {
                setBackgroundDrawableResource(android.R.color.transparent)
                setLayout((resources.displayMetrics.widthPixels * 0.92f).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
                addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND)
            }
            setOnDismissListener { premiumPaywallDialog = null }
            show()
            window?.setLayout((resources.displayMetrics.widthPixels * 0.92f).toInt(), ViewGroup.LayoutParams.WRAP_CONTENT)
        }
    }

'''
    s = s[:idx] + block + s[idx:]

# Release BillingClient cleanly with the activity.
if 'billingManager.endConnection()' not in s:
    destroy_anchor = '    override fun onDestroy() {\n'
    if destroy_anchor in s:
        s = s.replace(destroy_anchor, destroy_anchor + '        if (::billingManager.isInitialized) billingManager.endConnection()\n', 1)

p.write_text(s)
