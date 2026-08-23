// RideMesh Beta4.3 — public Google Play release candidate
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
        versionCode = 10
        versionName = "1.0.0-beta4.3-play"
    }

    buildFeatures {
        viewBinding = true
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
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

    // Legacy experimental mesh classes remain compiled for source continuity, but the
    // public Beta4.3 user flow does not expose or start that transport.
    implementation("com.google.android.gms:play-services-nearby:19.4.0")
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
    implementation("com.google.zxing:core:3.5.4")

    // Real-time Internet voice engine. Technical implementation details are intentionally
    // hidden from normal public UI; credentials and privileged backend logic are not embedded.
    implementation("io.github.webrtc-sdk:android:144.7559.09")

    testImplementation("junit:junit:4.13.2")
}
