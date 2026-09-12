# RideMesh iOS 1.0 Build 28 — App Review Checklist

## 1. Commercial account state
Confirm all are Active in App Store Connect > Business:
- Paid Apps Agreement
- Bank account
- U.S. Form W-8BEN
- U.S. Certificate of Foreign Status of Beneficial Owner

## 2. Subscription configuration
App Store Connect > RideMesh > Subscriptions > RideMesh Premium > RideMesh Monthly

Confirm:
- Product ID: `com.autopilotindia.ridemesh.monthly`
- Duration: 1 month
- Price: configured
- Intro offer: 1 week free trial (if still intended)
- Localization: complete
- Availability: matches the app's intended storefront availability
- Status has no Missing Metadata / Developer Action Needed warning

## 3. FIRST AUTO-RENEWABLE SUBSCRIPTION — CRITICAL
This is RideMesh's first auto-renewable subscription.

The following must be in the SAME App Review submission:
- iOS app version 1.0, build 28
- subscription group `RideMesh Premium`
- subscription `RideMesh Monthly`

From the subscription page use **Add for Review** and add it to the same draft submission as iOS 1.0 build 28 before pressing Submit for Review.

## 4. TestFlight verification before resubmission
Install build 28 from TestFlight and open the premium paywall.

PASS requires:
- localized monthly price appears
- free-trial text appears when the sandbox/TestFlight account is eligible
- purchase button says START FREE TRIAL or CONTINUE
- tapping it opens Apple's purchase confirmation sheet
- Restore Purchases is responsive

If StoreKit is temporarily unavailable, build 28 should show RETRY APP STORE instead of a dead CONTINUE button.

Do not submit until the price loads and Apple's purchase sheet opens at least once on a clean TestFlight installation.

## 5. Suggested App Review note
RideMesh Premium uses StoreKit 2 auto-renewable subscription product `com.autopilotindia.ridemesh.monthly`. Build 28 improves App Store catalog loading and retry behavior. To test, open RideMesh and tap Create Ride or Join Ride. If the account is not entitled, the premium paywall appears. The localized price is loaded from StoreKit. Tap START FREE TRIAL / CONTINUE to open Apple's purchase sheet. Restore Purchases is also available on the paywall.
