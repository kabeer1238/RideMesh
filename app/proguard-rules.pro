# RideMesh public release obfuscation rules.
# Keep WebRTC JNI-facing classes intact while allowing RideMesh application code to be optimized/obfuscated.
-keep class org.webrtc.** { *; }
-dontwarn org.webrtc.**
-keepattributes *Annotation*
-keepattributes Signature

# AndroidX / Google Play code scanner libraries supply their own consumer rules.
# Do not keep RideMesh app classes globally; R8 should optimize and obfuscate them.
