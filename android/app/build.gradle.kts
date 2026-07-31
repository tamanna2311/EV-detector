plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val releaseKeystorePath = providers.environmentVariable("EVTRACE_KEYSTORE_PATH").orNull
val releaseKeystorePassword =
    providers.environmentVariable("EVTRACE_KEYSTORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("EVTRACE_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("EVTRACE_KEY_PASSWORD").orNull
val hasReleaseSigning =
    listOf(
        releaseKeystorePath,
        releaseKeystorePassword,
        releaseKeyAlias,
        releaseKeyPassword,
    ).all { !it.isNullOrBlank() }

android {
    namespace = "com.evtrace.collector"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.evtrace.collector"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "android.test.InstrumentationTestRunner"
        buildConfigField(
            "String",
            "API_BASE_URL",
            "\"https://ev-detector.onrender.com\"",
        )
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = file(requireNotNull(releaseKeystorePath))
                storePassword = releaseKeystorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            if (hasReleaseSigning) {
                signingConfig = signingConfigs.getByName("release")
            }
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        buildConfig = true
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    lint {
        abortOnError = true
        checkReleaseBuilds = true
        warningsAsErrors = true
        disable += setOf("GradleDependency")
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}
