# Build 28 — Xcode build notes

1. On the Mac, extract this package.
2. In Terminal, `cd` into the extracted folder.
3. Generate the project with the same XcodeGen workflow used for build 27:
   `xcodegen generate`
4. Open `RideMeshIOS.xcodeproj` in Xcode.
5. Select the RideMeshIOS target > Signing & Capabilities.
6. Confirm Team is the correct paid Apple Developer team and Bundle Identifier is exactly `com.autopilotindia.ridemesh`.
7. If Xcode offers **In-App Purchase** under `+ Capability`, add it to the target. For an explicit App ID Apple enables In-App Purchase by default server-side; adding it in Xcode records the target capability in the generated project. If Xcode does not show it, do not invent an entitlement.
8. Confirm Version = 1.0 and Build = 28.
9. Product > Archive.
10. Validate App, then Distribute App > App Store Connect > Upload.
11. After processing, add build 28 to iOS 1.0.
12. Add the first subscription group + monthly subscription to the same App Review submission.
13. Test build 28 through TestFlight before resubmitting.

Do not use the DEBUG-PREMIUM-UNLOCK package for App Store distribution.
