plugins {
    id("com.android.application") version "9.4.1"
    // Cucumber-Android is built with Kotlin 2.4: the Kotlin the Android plugin compiles with must be at least as new
    id("org.jetbrains.kotlin.android") version "2.4.21" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.21"
}

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
    implementation(platform("androidx.compose:compose-bom:2026.09.00"))
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.13.0")

    testImplementation(platform("io.cucumber:cucumber-bom:8.0.4"))
    testImplementation("io.cucumber:cucumber-java")
    testImplementation("io.cucumber:cucumber-picocontainer")
    testImplementation("io.cucumber:cucumber-junit-platform-engine")
    testImplementation("org.junit.platform:junit-platform-suite")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")

    androidTestImplementation("io.cucumber:cucumber-android:7.19.0")
    androidTestImplementation("io.cucumber:cucumber-picocontainer:7.34.9")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.4.0")   // the screen steps
}
