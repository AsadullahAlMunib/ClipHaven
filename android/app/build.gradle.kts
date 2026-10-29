plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.asadullah.cliphaven"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.asadullah.cliphaven"
        minSdk = 24
        targetSdk = 34
        versionCode = 310
        versionName = "3.1.0"

        ndk {
            // Target 64-bit ARM (99%+ of modern Android devices), reducing APK size from ~140+ MB to ~35 MB
            // by excluding PC emulator (x86, x86_64) and duplicate 32-bit Python/FFmpeg archives.
            abiFilters.add("arm64-v8a")
        }
    }

    signingConfigs {
        create("releaseKey") {
            val ksFile = file(System.getenv("CLIPHAVEN_KEYSTORE_FILE") ?: "cliphaven-release.jks")
            if (ksFile.exists()) {
                storeFile = ksFile
                storePassword = System.getenv("CLIPHAVEN_KEYSTORE_PASSWORD") ?: "cliphaven2026"
                keyAlias = System.getenv("CLIPHAVEN_KEY_ALIAS") ?: "cliphaven"
                keyPassword = System.getenv("CLIPHAVEN_KEY_PASSWORD") ?: "cliphaven2026"
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            val relConfig = signingConfigs.findByName("releaseKey")
            signingConfig = if (relConfig?.storeFile?.exists() == true) {
                relConfig
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }
}

tasks.register<Copy>("syncWebAssets") {
    from("../../index.html", "../../style.css", "../../app.js", "../../logo.svg")
    into("src/main/assets")
}

tasks.named("preBuild") {
    dependsOn("syncWebAssets")
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.webkit:webkit:1.10.0")
    implementation("io.github.junkfood02.youtubedl-android:library:0.17.2")
    implementation("io.github.junkfood02.youtubedl-android:ffmpeg:0.17.2")
}
