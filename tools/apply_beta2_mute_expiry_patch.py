from pathlib import Path

root = Path(".")
build = (root / "app/build.gradle.kts").read_text()
layout = (root / "app/src/main/res/layout/activity_main.xml").read_text()
activity = (root / "app/src/main/java/com/bikemesh/ridemesh/MainActivity.kt").read_text()
audio = (root / "app/src/main/java/com/bikemesh/ridemesh/audio/AudioEngine.kt").read_text()
beta = root / "app/src/main/java/com/bikemesh/ridemesh/beta/BetaWindow.kt"

required = {
    "Beta2 version": 'versionName = "1.0.0-beta2"' in build,
    "API 36": "compileSdk = 36" in build and "targetSdk = 36" in build,
    "mute control": 'android:id="@+id/activeMute"' in layout and "setUserMuted" in audio,
    "60-day expiry": beta.exists() and "DURATION_DAYS = 60L" in beta.read_text(),
    "approved home UI": 'android:text="READY TO RIDE"' in layout and 'android:text="YOUR GROUP.' in layout,
    "approved active UI": 'android:text="RIDE ACTIVE"' in layout and "dp(72)" in activity,
    "single group": "secondaryInternetNode" not in activity and "SECONDARY GROUP" not in layout,
}

failed = [name for name, ok in required.items() if not ok]
if failed:
    raise SystemExit("RideMesh Beta2 source validation failed: " + ", ".join(failed))

print("RideMesh Beta2 approved UI, mute, expiry and single-group source already applied.")
