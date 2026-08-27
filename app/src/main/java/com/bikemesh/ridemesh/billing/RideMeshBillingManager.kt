package com.bikemesh.ridemesh.billing

import android.app.Activity
import android.content.Context
import com.android.billingclient.api.AcknowledgePurchaseParams
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams
import java.util.concurrent.atomic.AtomicBoolean

class RideMeshBillingManager(
    context: Context,
    private val onEntitlementChanged: (Boolean) -> Unit,
    private val onProductChanged: (SubscriptionDisplay?) -> Unit,
    private val onBillingMessage: (String) -> Unit,
) : PurchasesUpdatedListener {

    data class SubscriptionDisplay(
        val productDetails: ProductDetails,
        val offerToken: String,
        val localizedMonthlyPrice: String,
        val hasSevenDayTrial: Boolean,
    )

    private val appContext = context.applicationContext
    private var billingClient: BillingClient? = null
    private var subscription: SubscriptionDisplay? = null
    private val started = AtomicBoolean(false)

    @Volatile
    var hasPremiumEntitlement: Boolean = false
        private set

    fun start() {
        if (!started.compareAndSet(false, true)) return
        val client = BillingClient.newBuilder(appContext)
            .setListener(this)
            .enablePendingPurchases()
            .build()
        billingClient = client
        connect(client)
    }

    fun endConnection() {
        billingClient?.endConnection()
        billingClient = null
        started.set(false)
    }

    fun refresh() {
        val client = billingClient ?: return
        if (client.isReady) {
            queryExistingPurchases(client)
            querySubscriptionProduct(client)
        } else {
            connect(client)
        }
    }

    fun launchPurchase(activity: Activity): Boolean {
        val client = billingClient ?: return false
        val item = subscription ?: return false
        if (!client.isReady) return false
        val productParams = BillingFlowParams.ProductDetailsParams.newBuilder()
            .setProductDetails(item.productDetails)
            .setOfferToken(item.offerToken)
            .build()
        val flowParams = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(listOf(productParams))
            .build()
        val result = client.launchBillingFlow(activity, flowParams)
        if (result.responseCode != BillingClient.BillingResponseCode.OK) {
            onBillingMessage(result.debugMessage.ifBlank { "Unable to open Google Play checkout." })
            return false
        }
        return true
    }

    fun restorePurchases() {
        val client = billingClient ?: return
        if (!client.isReady) {
            onBillingMessage("Connecting to Google Play…")
            connect(client)
            return
        }
        queryExistingPurchases(client, showRestoreMessage = true)
    }

    private fun connect(client: BillingClient) {
        if (client.isReady) {
            queryExistingPurchases(client)
            querySubscriptionProduct(client)
            return
        }
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: BillingResult) {
                if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                    queryExistingPurchases(client)
                    querySubscriptionProduct(client)
                } else {
                    onBillingMessage("Google Play Billing unavailable: ${result.debugMessage}")
                }
            }

            override fun onBillingServiceDisconnected() {
                onBillingMessage("Google Play connection interrupted. We'll reconnect automatically.")
            }
        })
    }

    private fun querySubscriptionProduct(client: BillingClient) {
        val product = QueryProductDetailsParams.Product.newBuilder()
            .setProductId(PRODUCT_ID)
            .setProductType(BillingClient.ProductType.SUBS)
            .build()
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(listOf(product))
            .build()
        client.queryProductDetailsAsync(params) { result, products ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                onProductChanged(null)
                return@queryProductDetailsAsync
            }
            val details = products.firstOrNull() ?: run {
                subscription = null
                onProductChanged(null)
                return@queryProductDetailsAsync
            }
            val offer = details.subscriptionOfferDetails
                ?.firstOrNull { it.offerId != null && it.pricingPhases.pricingPhaseList.any { phase -> phase.priceAmountMicros == 0L && phase.billingPeriod == "P7D" } }
                ?: details.subscriptionOfferDetails?.firstOrNull()
            if (offer == null) {
                subscription = null
                onProductChanged(null)
                return@queryProductDetailsAsync
            }
            val phases = offer.pricingPhases.pricingPhaseList
            val paidPhase = phases.lastOrNull { it.priceAmountMicros > 0L } ?: phases.lastOrNull()
            if (paidPhase == null) {
                subscription = null
                onProductChanged(null)
                return@queryProductDetailsAsync
            }
            val display = SubscriptionDisplay(
                productDetails = details,
                offerToken = offer.offerToken,
                localizedMonthlyPrice = paidPhase.formattedPrice,
                hasSevenDayTrial = phases.any { it.priceAmountMicros == 0L && it.billingPeriod == "P7D" },
            )
            subscription = display
            onProductChanged(display)
        }
    }

    private fun queryExistingPurchases(client: BillingClient, showRestoreMessage: Boolean = false) {
        val params = QueryPurchasesParams.newBuilder()
            .setProductType(BillingClient.ProductType.SUBS)
            .build()
        client.queryPurchasesAsync(params) { result, purchases ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                if (showRestoreMessage) onBillingMessage("Couldn't check purchases. Please try again.")
                return@queryPurchasesAsync
            }
            val active = purchases.any { purchase ->
                purchase.products.contains(PRODUCT_ID) && purchase.purchaseState == Purchase.PurchaseState.PURCHASED
            }
            updateEntitlement(active)
            purchases.filter { it.purchaseState == Purchase.PurchaseState.PURCHASED && !it.isAcknowledged }
                .forEach { acknowledge(client, it) }
            if (showRestoreMessage) {
                onBillingMessage(if (active) "RideMesh Premium restored." else "No active RideMesh Premium subscription found.")
            }
        }
    }

    private fun acknowledge(client: BillingClient, purchase: Purchase) {
        val params = AcknowledgePurchaseParams.newBuilder()
            .setPurchaseToken(purchase.purchaseToken)
            .build()
        client.acknowledgePurchase(params) { result ->
            if (result.responseCode != BillingClient.BillingResponseCode.OK) {
                onBillingMessage("Purchase received. Google Play is still confirming it.")
            }
        }
    }

    override fun onPurchasesUpdated(result: BillingResult, purchases: MutableList<Purchase>?) {
        when (result.responseCode) {
            BillingClient.BillingResponseCode.OK -> {
                val client = billingClient ?: return
                val active = purchases.orEmpty().any { purchase ->
                    purchase.products.contains(PRODUCT_ID) && purchase.purchaseState == Purchase.PurchaseState.PURCHASED
                }
                updateEntitlement(active)
                purchases.orEmpty()
                    .filter { it.purchaseState == Purchase.PurchaseState.PURCHASED && !it.isAcknowledged }
                    .forEach { acknowledge(client, it) }
            }
            BillingClient.BillingResponseCode.USER_CANCELED -> Unit
            else -> onBillingMessage(result.debugMessage.ifBlank { "Google Play purchase couldn't be completed." })
        }
    }

    private fun updateEntitlement(active: Boolean) {
        if (hasPremiumEntitlement == active) return
        hasPremiumEntitlement = active
        onEntitlementChanged(active)
    }

    companion object {
        const val PRODUCT_ID = "ridemesh_premium_monthly"
    }
}
