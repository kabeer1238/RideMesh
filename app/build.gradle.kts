// RideMesh Beta4 — Internet-only WebRTC + Opus field test
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.bikemesh.ridemesh"
    compileSdk = 36

    defaultConfig {
        applicationId = "in.autopilotindia.ridemesh"
        minSdk = 26
        targetSdk = 36
        versionCode = 7
        versionName = "1.0.0-beta4-webrtc-opus"
    }

    buildFeatures {
        viewBinding = true
    }

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.fromTarget("17")
    }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.3")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.1")
    implementation("androidx.activity:activity-ktx:1.10.1")
    implementation("com.google.android.material:material:1.12.0")

    // Kept only because the preserved Beta3.x experimental mesh source still compiles in this branch.
    // Beta4's user-facing voice path does NOT start Nearby/local mesh.
    implementation("com.google.android.gms:play-services-nearby:19.4.0")
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
    implementation("com.google.zxing:core:3.5.4")

    // Current prebuilt libwebrtc Android AAR. WebRTC negotiates Opus for the audio track;
    // MQTT is used only for lightweight room presence and SDP/ICE signaling.
    implementation("io.github.webrtc-sdk:android:144.7559.09")

    testImplementation("junit:junit:4.13.2")
}
