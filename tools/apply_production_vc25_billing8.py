from pathlib import Path

# Production vc25 migration required by Google Play:
# - versionCode 25 (vc24 has already been uploaded to Play)
# - Google Play Billing Library 8.0.0
# - PBL 8 queryProductDetailsAsync and pending-purchases APIs

# The vc24 subscription patch runs immediately before this script, so migrate
# only the release-level billing/version pieces and leave the tested vc23 UI,
# paywall wording, 2-month P2M offer selection, support, voice and map logic intact.
gradle = Path("app/build.gradle.kts")
s = gradle.read_text()
s = s.replace("versionCode = 24", "versionCode = 25")
s = s.replace(
    'com.android.billingclient:billing-ktx:7.1.1',
    'com.android.billingclient:billing-ktx:8.0.0',
)
if 'versionCode = 25' not in s:
    raise SystemExit('vc25 migration failed: versionCode 25 missing')
if 'com.android.billingclient:billing-ktx:8.0.0' not in s:
    raise SystemExit('vc25 migration failed: Billing 8.0.0 dependency missing')
gradle.write_text(s)

manager = Path("app/src/main/java/com/bikemesh/ridemesh/billing/RideMeshBillingManager.kt")
m = manager.read_text()

if 'import com.android.billingclient.api.PendingPurchasesParams' not in m:
    m = m.replace(
        'import com.android.billingclient.api.ProductDetails\n',
        'import com.android.billingclient.api.ProductDetails\nimport com.android.billingclient.api.PendingPurchasesParams\n',
        1,
    )

m = m.replace(
    '''            .enablePendingPurchases()\n            .build()''',
    '''            .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())\n            .enableAutoServiceReconnection()\n            .build()''',
    1,
)

m = m.replace(
    '''        client.queryProductDetailsAsync(params) { result, products ->\n            if (result.responseCode != BillingClient.BillingResponseCode.OK) {''',
    '''        client.queryProductDetailsAsync(params) { result, queryResult ->\n            val products = queryResult.productDetailsList\n            if (result.responseCode != BillingClient.BillingResponseCode.OK) {''',
    1,
)

required = [
    'PendingPurchasesParams.newBuilder().enableOneTimeProducts().build()',
    '.enableAutoServiceReconnection()',
    'client.queryProductDetailsAsync(params) { result, queryResult ->',
    'val products = queryResult.productDetailsList',
    'billingPeriod == "P2M"',
    'const val PRODUCT_ID = "ridemesh_premium_monthly"',
]
for value in required:
    if value not in m:
        raise SystemExit(f'vc25 Billing 8 migration failed: missing {value}')

if '.enablePendingPurchases()' in m:
    raise SystemExit('vc25 Billing 8 migration failed: deprecated no-arg enablePendingPurchases remains')
if 'queryProductDetailsAsync(params) { result, products ->' in m:
    raise SystemExit('vc25 Billing 8 migration failed: PBL 7 product details callback remains')
if 'queryProductDetailsAsync(params) { queryResult ->' in m:
    raise SystemExit('vc25 Billing 8 migration failed: incorrect one-argument callback remains')

manager.write_text(m)
print('Production vc25 Billing 8.0.0 migration applied')
