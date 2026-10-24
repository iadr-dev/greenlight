plugins {
    id("com.android.application") version "9.4.1"
    // Cucumber-Android is built with Kotlin 2.4: the Kotlin the Android plugin compiles with must be at least as new
    id("org.jetbrains.kotlin.android") version "2.4.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.21"
}

// the versions the dependencies below are locked to (gradle.lockfile holds what they resolve to)
val composeBom = "2026.09.00"
val activityCompose = "1.13.0"
val cucumberBom = "8.0.4"
val cucumberAndroid = "7.19.0"
val cucumberJvmLine = "7.34.9"           // the Cucumber-JVM line Cucumber-Android is built on
val uiAutomator = "2.4.0"

apply(from = "greenlight.gradle.kts")
apply(from = "greenlight-device.gradle.kts")

android {
    namespace = "sample.ui"
    compileSdk = 37

    defaultConfig {
        applicationId = "sample.ui"
        minSdk = 26
        targetSdk = 37
        testInstrumentationRunner = "io.cucumber.android.runner.CucumberAndroidJUnitRunner"
        testInstrumentationRunnerArguments["optionsAnnotationPackage"] = "greenlight"
    }

    buildTypes {
        release {
            isMinifyEnabled = true                      // the release build is shrunk and obfuscated (it is never built by the tests)
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }

    buildFeatures {
        compose = true
    }

    sourceSets {
        getByName("androidTest") {
            kotlin.srcDir("src/test/kotlin")            // the same steps and drivers as the JVM run
            kotlin.srcDir("src/device/kotlin")          // the class that starts them on the device
            kotlin.srcDir("src/device-ui/kotlin")       // the screen steps (opt-in, with UI Automator below)
            assets.srcDir("src/test/resources")         // the same feature files, as assets/features
        }
    }
}

dependencyLocking {
    lockAllConfigurations()
    lockMode = LockMode.LENIENT
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:$composeBom"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:$activityCompose")

    testImplementation(platform("io.cucumber:cucumber-bom:$cucumberBom"))
    testImplementation("io.cucumber:cucumber-java")
    testImplementation("io.cucumber:cucumber-picocontainer")
    testImplementation("io.cucumber:cucumber-junit-platform-engine")
    testImplementation("org.junit.platform:junit-platform-suite")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")

    androidTestImplementation("io.cucumber:cucumber-android:$cucumberAndroid")
    androidTestImplementation("io.cucumber:cucumber-picocontainer:7.34.9")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:$uiAutomator")   // the screen steps
}
