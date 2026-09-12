package com.bikemesh.ridemesh.billing

import android.app.Activity
import android.content.Context

/** Offline testing adapter. No BillingClient SDK, connection or purchase UI. */
class RideMeshBillingManager(
    context: Context,
    private val onEntitlementChanged: (Boolean) -> Unit,
    private val onProductChanged: (SubscriptionDisplay?) -> Unit,
    private val onBillingMessage: (String) -> Unit,
) {
    data class SubscriptionDisplay(val localizedMonthlyPrice: String, val hasTwoMonthTrial: Boolean)
    val hasPremiumEntitlement = true
    fun start() = Unit
    fun endConnection() = Unit
    fun refresh() = Unit
    fun launchPurchase(activity: Activity): Boolean = false
    fun restorePurchases() = Unit
}
