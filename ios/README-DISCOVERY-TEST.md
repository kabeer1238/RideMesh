# Android 35 / iOS 33 discovery test

This is a diagnostic field build. Discovery and voice between physical phones have not been verified.

Changes: iOS reports advertising/discovery completion, separate start errors, detected/filtered/matching devices, connection attempts and transport links. Failed advertising/discovery starts retry every five seconds. Audio startup reactivates the existing session and retries up to four times; ending the ride or an interruption cancels retries. Audio errors no longer overwrite discovery errors. Both apps composite in-app logos with screen blending to remove their black matte. Android diagnostics use the installed version instead of a hardcoded build label.

Install Android vc35 and build/sign iOS vc33 from source in Xcode. Use NORMAL role on Android and Hybrid Voice enabled on iOS. Use the same ride code. Keep both apps foreground, within two metres, and Wi-Fi/Bluetooth on. Disable mobile data. Grant Nearby Devices/Location on Android and Bluetooth/Local Network/Microphone on iOS.

After 20 seconds, open Status on both phones. Record iOS advertising, discovery, seen, filtered, matching, pending and transport links, plus any error. If both report discovery on but seen remains zero, test while connected to the same Wi-Fi access point with its internet disconnected; record this separately from direct phone-to-phone testing. Same-LAN success does not establish direct radio or multi-hop support.

Test the built-in phone microphone/speaker first, then the helmet headset. Verify End Ride stops audio and discovery. Check the logo over the riding artwork and the iOS panels. Screen composition leaves the supplied artwork files intact and can lighten cyan slightly over coloured backgrounds.

Do not proceed to eight-rider range testing until bidirectional voice on two phones is stable. The unsigned iOS app needs Apple signing; the source is included for that purpose.
