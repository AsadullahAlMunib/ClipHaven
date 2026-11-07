plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.asadullahalmunib.cliphaven"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.asadullahalmunib.cliphaven"
        minSdk = 24
        targetSdk = 34
        versionCode = 322
        versionName = "3.2.2"
    }

    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "armeabi-v7a")
            isUniversalApk = false
        }
    }

    signingConfigs {
        create("releaseKey") {
            val ksPath = System.getenv("CLIPHAVEN_KEYSTORE_FILE")
            val ksPass = System.getenv("CLIPHAVEN_KEYSTORE_PASSWORD")
            val kAlias = System.getenv("CLIPHAVEN_KEY_ALIAS")
            val kPass = System.getenv("CLIPHAVEN_KEY_PASSWORD")
            if (!ksPath.isNullOrBlank() && file(ksPath).exists() && !ksPass.isNullOrBlank() && !kAlias.isNullOrBlank() && !kPass.isNullOrBlank()) {
                storeFile = file(ksPath)
                storePassword = ksPass
                keyAlias = kAlias
                keyPassword = kPass
                enableV1Signing = true
                enableV2Signing = true
            }
        }
    }

    buildTypes {
        release {
            // Keep R8 minification & resource shrinking disabled so youtubedl-android's
            // embedded Python/FFmpeg archives, Apache Commons Compress, and WebView JNI bridge are never stripped.
            isMinifyEnabled = false
            isShrinkResources = false
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

tasks.register("ensureXmlResources") {
    doLast {
        val xmlDir = file("src/main/res/xml")
        xmlDir.mkdirs()
        val filePaths = file("src/main/res/xml/file_paths.xml")
        if (!filePaths.exists()) {
            filePaths.writeText(
                """<?xml version="1.0" encoding="utf-8"?>
<paths>
    <cache-path name="updates" path="." />
    <files-path name="internal_files" path="." />
    <external-path name="external_storage" path="." />
    <external-files-path name="external_app_files" path="." />
</paths>
""".trimIndent()
            )
        }
    }
}

tasks.named("preBuild") {
    dependsOn("syncWebAssets", "ensureXmlResources")
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.webkit:webkit:1.10.0")
    implementation("io.github.junkfood02.youtubedl-android:library:0.18.1")
    implementation("io.github.junkfood02.youtubedl-android:ffmpeg:0.18.1")
}
