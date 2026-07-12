plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// LiteRT-LM (FunctionGemma) is an OPTIONAL build flavour:
//     gradle assembleDebug                    -> ships, structurer = keyword rules (badge "cpu")
//     gradle assembleDebug -PwithLlm=true     -> FunctionGemma 270M (badge "litert-gpu")
// The llm/ source set is compiled ONLY with -PwithLlm so a dependency-resolution
// failure can never block the demo build. Badges stay honest either way:
// StructurerFactory reflects the LLM impl in, and falls back if it is absent.
val withLlm = providers.gradleProperty("withLlm").orNull == "true"

android {
    namespace = "com.crowdvision.field"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.crowdvision.field"
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
        // Read by BuildConfig so the UI can state which structurer is compiled in.
        buildConfigField("boolean", "WITH_LLM", withLlm.toString())
    }

    buildFeatures {
        buildConfig = true
    }

    sourceSets["main"].java.srcDir("src/main/java")
    if (withLlm) {
        sourceSets["main"].java.srcDir("src/llm/java")
    }

    signingConfigs {
        // The release APK is DEBUG-SIGNED on purpose: it must be installable
        // straight from GitHub Releases at the demo. Stated in the release notes.
        create("releaseDebugSigned") {
            storeFile = file(System.getProperty("user.home") + "/.android/debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("releaseDebugSigned")
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
        resources.excludes += setOf("META-INF/INDEX.LIST", "META-INF/io.netty.versions.properties")
    }
    testOptions {
        unitTests.isReturnDefaultValues = true   // android.util.Log is a stub off-device
    }
}

dependencies {
    implementation("androidx.appcompat:appcompat:1.7.0")
    // Eclipse Paho JAVA client (NOT the dead org.eclipse.paho.android.service,
    // which breaks on API 31+). We own the lifecycle in FieldService.
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")

    // Unit tests run the real Envelope/Schema/Structurer code on the JVM, where
    // android.jar's org.json is a stub — so bring in the real one.
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")

    if (withLlm) {
        // LiteRT-LM: the .litertlm runtime for FunctionGemma 270M.
        // If the Maven coordinate does not resolve in your environment, drop the
        // LiteRT-LM AAR from the official release into app/libs/ — the fileTree
        // below picks it up and FunctionGemmaStructurer compiles unchanged.
        implementation("com.google.ai.edge.litert:litert:2.1.4")
        implementation(fileTree(mapOf("dir" to "libs", "include" to listOf("*.aar", "*.jar"))))
    }
}
