from pathlib import Path

# Beta5.5 / vc24 — Google Play Billing subscription gate.
# The 2-month free trial and regional prices are configured in Play Console.
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

# Add a real full-screen Premium page to the existing activity layout. It stays hidden
# until a non-entitled rider attempts CREATE, JOIN or START RIDE.
layout = Path("app/src/main/res/layout/activity_main.xml")
xml = layout.read_text()
if 'android:id="@+id/screenPremium"' not in xml:
    premium_page = r'''

    <!-- RIDEMESH PREMIUM / SUBSCRIPTION -->
    <ScrollView
        android:id="@+id/screenPremium"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:background="@color/black"
        android:fillViewport="true"
        android:overScrollMode="never"
        android:visibility="gone">

        <LinearLayout
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:orientation="vertical"
            android:paddingStart="22dp"
            android:paddingTop="16dp"
            android:paddingEnd="22dp"
            android:paddingBottom="30dp">

            <com.google.android.material.button.MaterialButton
                android:id="@+id/premiumBack"
                style="@style/Widget.MaterialComponents.Button.TextButton"
                android:layout_width="wrap_content"
                android:layout_height="44dp"
                android:minWidth="0dp"
                android:paddingStart="6dp"
                android:paddingEnd="12dp"
                android:text="‹  BACK"
                android:textColor="@color/muted"
                android:textSize="11sp" />

            <ImageView
                android:layout_width="match_parent"
                android:layout_height="84dp"
                android:layout_marginTop="6dp"
                android:contentDescription="RideMesh by Autopilot India"
                android:scaleType="fitCenter"
                android:src="@drawable/ridemesh_logo_exact" />

            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="12dp"
                android:fontFamily="sans-serif-condensed"
                android:gravity="center"
                android:letterSpacing="0.06"
                android:text="RIDEMESH PREMIUM"
                android:textColor="@color/white"
                android:textSize="30sp"
                android:textStyle="bold" />

            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="4dp"
                android:gravity="center"
                android:text="Ride together. Stay connected."
                android:textColor="@color/muted"
                android:textSize="14sp" />

            <TextView
                android:id="@+id/premiumTrialTitle"
                android:layout_width="wrap_content"
                android:layout_height="42dp"
                android:layout_gravity="center_horizontal"
                android:layout_marginTop="20dp"
                android:background="@drawable/hero_badge_bg"
                android:gravity="center"
                android:paddingStart="20dp"
                android:paddingEnd="20dp"
                android:text="RIDEMESH PREMIUM"
                android:textColor="@color/accent"
                android:textSize="15sp"
                android:textStyle="bold" />

            <TextView
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="22dp"
                android:fontFamily="sans-serif-condensed"
                android:gravity="center"
                android:letterSpacing="0.03"
                android:text="PREMIUM COMMUNICATION FOR EVERY RIDE"
                android:textColor="@color/white"
                android:textSize="17sp"
                android:textStyle="bold" />

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="16dp"
                android:background="@drawable/status_card_bg"
                android:orientation="vertical"
                android:padding="16dp">

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:text="HANDS-FREE GROUP VOICE"
                    android:textColor="@color/accent"
                    android:textSize="13sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="5dp"
                    android:text="Stay connected with your riding group without holding a push-to-talk button."
                    android:textColor="@color/white_soft"
                    android:textSize="12.5sp" />
            </LinearLayout>

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="10dp"
                android:background="@drawable/status_card_bg"
                android:orientation="vertical"
                android:padding="16dp">

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:text="LIVE RIDER MAP"
                    android:textColor="@color/accent"
                    android:textSize="13sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="5dp"
                    android:text="See riders and live ride information while your group is connected."
                    android:textColor="@color/white_soft"
                    android:textSize="12.5sp" />
            </LinearLayout>

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="10dp"
                android:background="@drawable/status_card_bg"
                android:orientation="vertical"
                android:padding="16dp">

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:text="RIDER STATUS"
                    android:textColor="@color/accent"
                    android:textSize="13sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="5dp"
                    android:text="View connection, rider distance and useful group status at a glance."
                    android:textColor="@color/white_soft"
                    android:textSize="12.5sp" />
            </LinearLayout>

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="10dp"
                android:background="@drawable/status_card_bg"
                android:orientation="vertical"
                android:padding="16dp">

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:text="HELMET AUDIO"
                    android:textColor="@color/accent"
                    android:textSize="13sp"
                    android:textStyle="bold" />

                <TextView
                    android:layout_width="match_parent"
                    android:layout_height="wrap_content"
                    android:layout_marginTop="5dp"
                    android:text="Designed to work with compatible Bluetooth riding headsets."
                    android:textColor="@color/white_soft"
                    android:textSize="12.5sp" />
            </LinearLayout>

            <TextView
                android:id="@+id/premiumPrice"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="24dp"
                android:gravity="center"
                android:lineSpacingExtra="3dp"
                android:text="Connecting to Google Play for your local price…"
                android:textColor="@color/white"
                android:textSize="21sp"
                android:textStyle="bold" />

            <TextView
                android:id="@+id/premiumDisclosure"
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="10dp"
                android:gravity="center"
                android:lineSpacingExtra="2dp"
                android:text="Your exact local price is provided by Google Play before purchase. Subscription renews monthly unless cancelled. Cancel anytime in Google Play."
                android:textColor="@color/muted"
                android:textSize="11.5sp" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/premiumPrimary"
                android:layout_width="match_parent"
                android:layout_height="58dp"
                android:layout_marginTop="22dp"
                android:text="RETRY GOOGLE PLAY"
                android:textColor="@color/black"
                android:textSize="12sp"
                android:textStyle="bold"
                app:backgroundTint="@color/accent"
                app:cornerRadius="16dp" />

            <com.google.android.material.button.MaterialButton
                android:id="@+id/premiumRestore"
                style="@style/Widget.MaterialComponents.Button.OutlinedButton"
                android:layout_width="match_parent"
                android:layout_height="52dp"
                android:layout_marginTop="10dp"
                android:text="RESTORE PURCHASE"
                android:textColor="@color/white"
                android:textSize="11sp"
                app:backgroundTint="@android:color/transparent"
                app:cornerRadius="16dp"
                app:strokeColor="@color/muted"
                app:strokeWidth="1dp" />

            <LinearLayout
                android:layout_width="match_parent"
                android:layout_height="wrap_content"
                android:layout_marginTop="12dp"
                android:gravity="center"
                android:orientation="horizontal">

                <TextView
                    android:id="@+id/premiumPrivacy"
                    android:layout_width="wrap_content"
                    android:layout_height="42dp"
                    android:gravity="center"
                    android:paddingStart="10dp"
                    android:paddingEnd="10dp"
                    android:text="PRIVACY POLICY"
                    android:textColor="@color/accent"
                    android:textSize="10.5sp" />

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="42dp"
                    android:gravity="center"
                    android:text="•"
                    android:textColor="@color/muted"
                    android:textSize="12sp" />

                <TextView
                    android:id="@+id/premiumTerms"
                    android:layout_width="wrap_content"
                    android:layout_height="42dp"
                    android:gravity="center"
                    android:paddingStart="10dp"
                    android:paddingEnd="10dp"
                    android:text="TERMS"
                    android:textColor="@color/accent"
                    android:textSize="10.5sp" />
            </LinearLayout>
        </LinearLayout>
    </ScrollView>
'''
    head, tail = xml.rsplit('</FrameLayout>', 1)
    xml = head + premium_page + '\n</FrameLayout>' + tail
    layout.write_text(xml)

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
        '    private lateinit var audioEngine: AudioEngine\n    private lateinit var billingManager: RideMeshBillingManager\n    private var billingProduct: RideMeshBillingManager.SubscriptionDisplay? = null\n    private var premiumEntryAction = PremiumEntryAction.NONE\n',
    )

s = s.replace(
    '    private enum class Screen { HOME, SETUP, ACTIVE }\n',
    '    private enum class Screen { HOME, SETUP, ACTIVE, PREMIUM }\n    private enum class PremiumEntryAction { NONE, CREATE_RIDE, JOIN_RIDE, START_RIDE }\n',
    1,
)

billing_init = '''\n        billingManager = RideMeshBillingManager(\n            context = this,\n            onEntitlementChanged = { active ->\n                runOnUiThread {\n                    if (active) continueAfterPremiumUnlock()\n                }\n            },\n            onProductChanged = { product ->\n                runOnUiThread {\n                    billingProduct = product\n                    renderPremiumPage()\n                }\n            },\n            onBillingMessage = { message ->\n                runOnUiThread { android.widget.Toast.makeText(this, message, android.widget.Toast.LENGTH_LONG).show() }\n            },\n        )\n        billingManager.start()\n'''
if 'billingManager = RideMeshBillingManager(' not in s:
    anchor = '        applyPowerUi()\n'
    if anchor not in s:
        raise SystemExit('onCreate billing init anchor not found')
    s = s.replace(anchor, anchor + billing_init, 1)

s = s.replace(
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            binding.setupTitle.text = "CREATE RIDE"',
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            premiumEntryAction = PremiumEntryAction.CREATE_RIDE\n            if (!ensurePremiumAccess()) return@setOnClickListener\n            premiumEntryAction = PremiumEntryAction.NONE\n            binding.setupTitle.text = "CREATE RIDE"',
    1,
)
s = s.replace(
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            binding.setupTitle.text = "JOIN RIDE"',
    '            if (!ensureBetaUsable()) return@setOnClickListener\n            premiumEntryAction = PremiumEntryAction.JOIN_RIDE\n            if (!ensurePremiumAccess()) return@setOnClickListener\n            premiumEntryAction = PremiumEntryAction.NONE\n            binding.setupTitle.text = "JOIN RIDE"',
    1,
)

premium_listeners = '''\n        binding.premiumBack.setOnClickListener {\n            premiumEntryAction = PremiumEntryAction.NONE\n            showScreen(Screen.HOME)\n        }\n        binding.premiumPrimary.setOnClickListener {\n            val product = billingProduct\n            if (product == null) {\n                billingManager.refresh()\n            } else {\n                billingManager.launchPurchase(this)\n            }\n        }\n        binding.premiumRestore.setOnClickListener { billingManager.restorePurchases() }\n        binding.premiumPrivacy.setOnClickListener {\n            runCatching {\n                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://autopilotindia.com/ridemesh-privacy-policy/")))\n            }\n        }\n        binding.premiumTerms.setOnClickListener {\n            runCatching {\n                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://play.google.com/about/play-terms/")))\n            }\n        }\n'''
if 'binding.premiumBack.setOnClickListener' not in s:
    anchor = '        binding.backHome.setOnClickListener {\n'
    if anchor not in s:
        raise SystemExit('premium listener anchor not found')
    s = s.replace(anchor, premium_listeners + '\n' + anchor, 1)

s = s.replace(
    '        binding.screenActive.visibility = if (screen == Screen.ACTIVE) View.VISIBLE else View.GONE\n',
    '        binding.screenActive.visibility = if (screen == Screen.ACTIVE) View.VISIBLE else View.GONE\n        binding.screenPremium.visibility = if (screen == Screen.PREMIUM) View.VISIBLE else View.GONE\n',
    1,
)

if 'private fun ensurePremiumAccess()' not in s:
    marker = '    private fun showSettingsAndHelpDialog()'
    idx = s.find(marker)
    if idx < 0:
        raise SystemExit('settings method anchor not found')
    block = r'''    private fun ensurePremiumAccess(): Boolean {
        if (::billingManager.isInitialized && billingManager.hasPremiumEntitlement) {
            premiumEntryAction = PremiumEntryAction.NONE
            return true
        }
        if (premiumEntryAction == PremiumEntryAction.NONE) {
            premiumEntryAction = PremiumEntryAction.START_RIDE
        }
        showPremiumPaywall()
        return false
    }

    private fun showPremiumPaywall() {
        if (isFinishing || isDestroyed) return
        renderPremiumPage()
        showScreen(Screen.PREMIUM)
    }

    private fun renderPremiumPage() {
        if (!::binding.isInitialized) return
        val product = billingProduct
        binding.premiumTrialTitle.text = if (product?.hasTwoMonthTrial == true) "2 MONTHS FREE" else "RIDEMESH PREMIUM"
        binding.premiumPrice.text = when {
            product == null -> "Connecting to Google Play for your local price…"
            product.hasTwoMonthTrial -> "FREE FOR 2 MONTHS\nThen ${product.localizedMonthlyPrice} / month"
            else -> "${product.localizedMonthlyPrice} / month"
        }
        binding.premiumPrimary.text = when {
            product == null -> "RETRY GOOGLE PLAY"
            product.hasTwoMonthTrial -> "START 2-MONTH FREE TRIAL"
            else -> "CONTINUE WITH PREMIUM"
        }
        binding.premiumDisclosure.text = when {
            product?.hasTwoMonthTrial == true -> "Free for 2 months, then ${product.localizedMonthlyPrice} per month. Subscription renews monthly unless cancelled. Cancel anytime in Google Play."
            product != null -> "${product.localizedMonthlyPrice} per month. Subscription renews monthly unless cancelled. Cancel anytime in Google Play."
            else -> "Your exact local price and eligibility are provided by Google Play before purchase. Subscription renews monthly unless cancelled."
        }
    }

    private fun continueAfterPremiumUnlock() {
        val action = premiumEntryAction
        if (action == PremiumEntryAction.NONE) return
        premiumEntryAction = PremiumEntryAction.NONE
        when (action) {
            PremiumEntryAction.CREATE_RIDE -> {
                binding.setupTitle.text = "CREATE RIDE"
                binding.rideCode.setText(generateRideCode())
                showScreen(Screen.SETUP)
            }
            PremiumEntryAction.JOIN_RIDE -> {
                binding.setupTitle.text = "JOIN RIDE"
                showScreen(Screen.SETUP)
                binding.rideCode.requestFocus()
            }
            PremiumEntryAction.START_RIDE -> {
                showScreen(Screen.SETUP)
                ensurePermissionsAndRun(PendingAction.START_RIDE)
            }
            PremiumEntryAction.NONE -> Unit
        }
    }

'''
    s = s[:idx] + block + s[idx:]

# Release BillingClient cleanly with the activity.
if 'billingManager.endConnection()' not in s:
    destroy_anchor = '    override fun onDestroy() {\n'
    if destroy_anchor in s:
        s = s.replace(destroy_anchor, destroy_anchor + '        if (::billingManager.isInitialized) billingManager.endConnection()\n', 1)

# Fail this materialization immediately if the Premium page was not wired into all key paths.
required_main = [
    'PremiumEntryAction.CREATE_RIDE',
    'PremiumEntryAction.JOIN_RIDE',
    'PremiumEntryAction.START_RIDE',
    'binding.screenPremium.visibility',
    'binding.premiumPrimary.setOnClickListener',
    'START 2-MONTH FREE TRIAL',
    'continueAfterPremiumUnlock()',
]
for value in required_main:
    if value not in s:
        raise SystemExit(f'Premium page source materialization missing: {value}')

required_layout = [
    'android:id="@+id/screenPremium"',
    'android:id="@+id/premiumTrialTitle"',
    'android:id="@+id/premiumPrice"',
    'android:id="@+id/premiumPrimary"',
    'android:id="@+id/premiumRestore"',
]
for value in required_layout:
    if value not in layout.read_text():
        raise SystemExit(f'Premium page layout materialization missing: {value}')

p.write_text(s)
