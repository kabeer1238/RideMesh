// RideMesh Beta4.2 — Google Play release candidate: Internet-only WebRTC + Opus
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
        versionCode = 9
        versionName = "1.0.0-beta4.2-play"
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

    // Preserved Beta3.x mesh classes still compile in this branch, but Beta4.2 does not
    // request Nearby permissions or start the local/offline transport in the user flow.
    implementation("com.google.android.gms:play-services-nearby:19.4.0")
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
    implementation("com.google.zxing:core:3.5.4")

    // WebRTC negotiates Opus for the audio track. MQTT/TLS is used only for lightweight
    // presence and SDP/ICE signaling; it is not the voice-media transport.
    implementation("io.github.webrtc-sdk:android:144.7559.09")

    testImplementation("junit:junit:4.13.2")
}
