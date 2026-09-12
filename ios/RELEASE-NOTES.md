# RideMesh iOS 1.0 — Build 28
## StoreKit Resilience / App Review Fix

This build is based directly on the App Store build 27 source.

### App Review issue addressed
Build 27 intentionally disabled the purchase button whenever StoreKit had not returned the monthly subscription product. During App Review the product catalog did not load, so the reviewer saw no localized price and an unresponsive-looking CONTINUE button.

### Build 28 changes
- Keeps the production StoreKit 2 product ID exactly:
  - `com.autopilotindia.ridemesh.monthly`
- Adds a bounded StoreKit catalog retry sequence instead of a single product request.
- Prevents overlapping product-catalog requests when multiple screens refresh at once.
- Rechecks the StoreKit catalog when the app becomes active and the product is still unavailable.
- Replaces the dead-end disabled CONTINUE state with a user-actionable **RETRY APP STORE** state.
- Shows **CONNECTING TO APP STORE…** only while a catalog request is actively running.
- Keeps price and free-trial text fully dynamic from Apple's returned `Product`.
- Keeps purchase verification and entitlement checks based on verified StoreKit 2 transactions.
- Keeps Restore Purchases and Manage Subscription behavior.
- Explicitly links `StoreKit.framework` in the generated Xcode project spec.
- Bumps build number from 27 to 28.

### Not changed
- Marketing version remains **1.0**.
- Bundle ID remains `com.autopilotindia.ridemesh`.
- No debug premium bypass is included.
- No local subscription timer is included.
- Ride/voice/map/location behavior is unchanged.

### Important
The code can recover from temporary catalog/service delays, but StoreKit still requires the subscription to be correctly configured in App Store Connect. Before App Review, follow `APP-REVIEW-vc28-CHECKLIST.md`.
