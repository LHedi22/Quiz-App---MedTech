import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Subtask 10.3 release-signing placeholder: real store-submission signing needs
// a keystore that must never be generated blindly or committed to the repo -
// it's a credential, not an implementation detail (CLAUDE.md Section 6). This
// loads one from `android/key.properties` (gitignored - see key.properties.example
// for the expected format) if present, and falls back to debug signing
// otherwise, so `flutter build apk --release` keeps working out of the box on
// a machine with no real keystore, exactly as it did before this change.
val keystorePropertiesFile = rootProject.file("key.properties")
val keystoreProperties = Properties()
val hasReleaseKeystore = keystorePropertiesFile.exists()
if (hasReleaseKeystore) {
    keystoreProperties.load(keystorePropertiesFile.inputStream())
}

android {
    namespace = "com.medtech.examscanner.exam_scanner_mobile"
    compileSdk = flutter.compileSdkVersion
    // No ndkVersion: this project has no native (C/C++/JNI) code, and the
    // NDK component this machine's Android SDK partially downloaded
    // (28.2.13676358) is corrupt (missing source.properties, verified by
    // inspecting the SDK's ndk/ directory directly) - declaring an NDK
    // requirement here just to satisfy AGP's default, for a version that
    // nothing in this app actually compiles against, isn't worth chasing a
    // full NDK re-download for.

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.medtech.examscanner.exam_scanner_mobile"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hasReleaseKeystore) {
            create("release") {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            // Real signing when android/key.properties supplies a release
            // keystore; falls back to debug keys otherwise (see comment above).
            signingConfig = if (hasReleaseKeystore) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
