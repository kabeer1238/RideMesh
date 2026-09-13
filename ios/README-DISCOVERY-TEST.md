# Android 36 / iOS 34 audio and discovery test

These builds default to normal online voice on first launch after this update, including when upgrading older hybrid test builds. Android: Settings > Voice connection > Internet voice; iOS: Hybrid Voice off. To run the offline tests, explicitly choose Offline mesh or Hybrid on Android and enable Hybrid Voice on iOS. These preferences persist after selection.

On shared Wi-Fi, leave BLE-only discovery off. Start the same ride on both phones. Open Status and send a two-second test tone from each phone in turn, listening on the other phone at low volume. Tone generation respects mute and End Ride. Reopen Android Status after the tone to refresh its snapshot. Record capture buffers/level, encoded/sent, received, decoded and errors. A received/decoded tone with no microphone voice narrows the fault to capture. An encoded tone with zero reception narrows it to the sending/routing/receiving path. Counters do not prove audible playback.

For direct-discovery isolation, end both rides, enable BLE-only discovery test in both Settings screens, and retry without a shared Wi-Fi network. This is experimental and does not establish cross-platform Bluetooth compatibility or range. Turn it off to return to shared-LAN discovery. The SDK-managed WebRTC medium is excluded from iOS Nearby discovery; the app's separate internet bridge is unchanged.

The bottom 12 percent of the wide in-app logo artwork is masked to remove the stray white marks; the source art and lettering remain intact. iOS explicitly connects the audio mixer to output and performs at most two recoveries if a running engine produces no microphone buffers for three seconds. Native-libopus-to-Android codec fixtures are included in the Android unit suite. Physical voice and direct offline mesh are still unverified.

This is a diagnostic field build. Discovery and voice between physical phones have not been verified.

Changes: iOS reports advertising/discovery completion, separate start errors, detected/filtered/matching devices, connection attempts and transport links. Failed advertising/discovery starts retry every five seconds. Audio startup reactivates the existing session and retries up to four times; ending the ride or an interruption cancels retries. Audio errors no longer overwrite discovery errors. Both apps composite in-app logos with screen blending to remove their black matte. Android diagnostics use the installed version instead of a hardcoded build label.

Install Android vc36 and build/sign iOS vc34 from source in Xcode. Use NORMAL role on Android and Hybrid Voice enabled on iOS for offline tests. Use the same ride code. Keep both apps foreground, within two metres, and Wi-Fi/Bluetooth on. Disable mobile data. Grant Nearby Devices/Location on Android and Bluetooth/Local Network/Microphone on iOS.

After 20 seconds, open Status on both phones. Record iOS advertising, discovery, seen, filtered, matching, pending and transport links, plus any error. If both report discovery on but seen remains zero, test while connected to the same Wi-Fi access point with its internet disconnected; record this separately from direct phone-to-phone testing. Same-LAN success does not establish direct radio or multi-hop support.

Test the built-in phone microphone/speaker first, then the helmet headset. Verify End Ride stops audio and discovery. Check the logo over the riding artwork and the iOS panels. Screen composition leaves the supplied artwork files intact and can lighten cyan slightly over coloured backgrounds.

Do not proceed to eight-rider range testing until bidirectional voice on two phones is stable. The unsigned iOS app needs Apple signing; the source is included for that purpose.
