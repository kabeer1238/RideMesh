# RideMesh iOS — v1.0 vc27 Liquid Glass + StoreKit Premium

Marketing version: **1.0**  
Build: **27**  
Bundle ID: **com.autopilotindia.ridemesh**  
Subscription product: **com.autopilotindia.ridemesh.monthly**

vc27 is the App Store subscription build for RideMesh by Autopilot India. It preserves the existing WebRTC/Opus voice, signaling, live location wire format, clustered rider map and rider contact actions, while adding a native StoreKit 2 subscription layer and a full iOS Liquid Glass visual refresh.

## What changed

### RideMesh Premium
- New premium paywall with RideMesh black/cyan branding.
- StoreKit 2 product loading from App Store Connect.
- Localized App Store price using `Product.displayPrice` — no hard-coded ₹ price.
- Reads introductory-offer eligibility from StoreKit.
- Shows the configured free trial only to eligible users.
- Purchase, Restore Purchases and Manage Subscription support.
- Entitlement verification uses verified StoreKit transactions.
- New rides are gated behind an active entitlement; an already-active ride is never abruptly stopped if entitlement state changes while the rider is on the road.
- Privacy Policy and Apple Standard EULA links are available directly from the paywall and Settings.

### iOS Liquid Glass redesign
- iOS 26 uses native `glassEffect` / Liquid Glass styling for RideMesh panels and controls.
- iOS 16–25 use a native material fallback so the app still looks consistent.
- Floating glass active-ride tab bar: RIDE / MAP / RIDERS / SETTINGS.
- Glass rider cards, map status overlays, rider detail panel, modal panels and settings sections.
- Deep graphite background with restrained cyan atmospheric glow.
- RideMesh cyan remains the connection/action color; glass is used selectively so map and voice status remain readable.

### Preserved from vc26
- Compact rider labels and map clustering.
- Cluster expand/collapse behavior.
- Rider detail X close, swipe-down and idle auto-hide.
- Optional phone sharing.
- Google Maps external navigation.
- WhatsApp / normal call and WhatsApp / SMS choices.
- Existing WebRTC/Opus voice path, Smart Ducking, Motorcycle Noise Guard, reconnection behavior, audio route handling and location protocol.

## Build

This source uses iOS 26 Liquid Glass APIs behind availability checks, so generate/build the project with **Xcode 26 or newer**.

```bash
cd "/path/to/RideMeshIOS-v1.0-vc27-LiquidGlass-StoreKit"
xcodegen generate
open RideMeshIOS.xcodeproj
```

In Xcode confirm:
- Version: **1.0**
- Build: **27**
- Automatically manage signing: ON
- Team: your Apple Developer team
- Bundle ID: **com.autopilotindia.ridemesh**

Then Archive and upload build **1.0 (27)** to App Store Connect.

## App Store Connect dependency

The code expects the auto-renewable subscription product ID:

`com.autopilotindia.ridemesh.monthly`

The intended introductory offer is:

**Free Trial → 1 Week → then monthly renewal**

The price is not hard-coded. StoreKit displays the user’s local App Store price, including the India price you configure in App Store Connect.
