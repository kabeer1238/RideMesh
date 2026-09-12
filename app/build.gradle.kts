// RideMesh Beta4.4.1 — crash-fix APK field candidate
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
        versionCode = 34
        versionName = "1.0.5-hybrid8-ios-test"
        manifestPlaceholders["MAPS_API_KEY"] =
            (project.findProperty("MAPS_API_KEY") as String?)
                ?: System.getenv("MAPS_API_KEY")
                ?: ""
    }

    buildFeatures {
        viewBinding = true
        buildConfig = true
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".offline"
        }
        release {
            // Deliberately disabled for this APK-only field test. Beta4.3/4.4 crashes began
            // after release minification was introduced, while the earlier WebRTC tester was
            // unminified. Re-enable only after phone validation and narrowed keep rules.
            isMinifyEnabled = false
            isShrinkResources = false
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
    implementation("com.plasmoverse:concentus:1.0.0")

    implementation("com.google.android.gms:play-services-nearby:19.4.0")
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
    implementation("com.google.android.gms:play-services-maps:19.2.0")
    implementation("com.google.android.gms:play-services-location:21.3.0")
    implementation("com.google.zxing:core:3.5.4")
    implementation("io.github.webrtc-sdk:android:144.7559.09")

    testImplementation("junit:junit:4.13.2")
}

// Explicit filename for field-test build identification.
android.applicationVariants.all {
    outputs.all {
        (this as com.android.build.gradle.internal.api.BaseVariantOutputImpl).outputFileName =
            "RideMesh-hybrid8-vc34-${buildType.name}.apk"
    }
}
