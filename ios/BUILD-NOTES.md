# RideMesh iOS v1.0 vc27 Build Notes

- Marketing version: **1.0**
- Build number: **27**
- Package: **RideMeshIOS-v1.0-vc27-LiquidGlass-StoreKit**
- Bundle ID: **com.autopilotindia.ridemesh**
- StoreKit product ID: **com.autopilotindia.ridemesh.monthly**
- Deployment target: iOS 16.0
- Build SDK: Xcode 26 / iOS 26 SDK or newer recommended

## Pre-upload checklist
1. Run `xcodegen generate`.
2. Open `RideMeshIOS.xcodeproj`.
3. Confirm Version 1.0 / Build 27.
4. Confirm automatic signing and the correct Apple Developer team.
5. Run on a real iPhone while signed into a Sandbox/TestFlight-compatible App Store account.
6. Confirm the Premium screen loads the real App Store monthly product and local price.
7. Confirm the introductory offer shows **1 WEEK FREE** only when the StoreKit sandbox account is eligible.
8. Complete a sandbox subscription purchase.
9. Confirm Create Ride and Join Ride are unlocked after verified purchase.
10. Confirm Restore Purchases restores access after reinstall/sign-in changes.
11. Confirm Manage Subscription opens Apple’s subscription management sheet.
12. Test a two-device RideMesh ride after subscription unlock.
13. Archive and upload build 1.0 (27).

## App Review subscription screenshot
Do not upload a mock marketing image as the subscription review screenshot. After vc27 is running on an iPhone, open the real **RideMesh Premium** paywall and take an iPhone screenshot. Upload that screenshot to the subscription’s **Review Information → Screenshot** field in App Store Connect.

The screenshot should visibly show the real in-app subscription experience, including the Premium title, free-trial/price information loaded from StoreKit, Start Free Trial/Continue action, Restore Purchases and legal links.
