plugins {
    id("com.android.library") version "9.4.1"
    // Cucumber-Android is built with Kotlin 2.4: the Kotlin the Android plugin compiles with must be at least as new
    id("org.jetbrains.kotlin.android") version "2.4.21" apply false
}

apply(from = "greenlight.gradle.kts")
apply(from = "greenlight-device.gradle.kts")

android {
    namespace = "contract"
    compileSdk = 37                                    // Cucumber-Android 7.19 needs 37 to compile against

    defaultConfig {
        minSdk = 26                                    // Cucumber-Android runs on API 26 and newer
        testInstrumentationRunner = "io.cucumber.android.runner.CucumberAndroidJUnitRunner"
        testInstrumentationRunnerArguments["optionsAnnotationPackage"] = "greenlight"
    }

    sourceSets {
        getByName("androidTest") {
            kotlin.srcDir("src/test/kotlin")            // the same steps and drivers as the JVM run
            kotlin.srcDir("src/device/kotlin")          // the class that starts them on the device
            assets.srcDir("src/test/resources")         // the same feature files, as assets/features
        }
    }
}

dependencyLocking {
    lockAllConfigurations()          // the resolved versions are in gradle.lockfile: a run never picks up a newer one
    lockMode = LockMode.LENIENT      // the Android plugin makes configurations of its own; those without a lock are not an error
}

dependencies {
    testImplementation(platform("io.cucumber:cucumber-bom:8.0.4"))
    testImplementation("io.cucumber:cucumber-java")
    testImplementation("io.cucumber:cucumber-picocontainer")
    testImplementation("io.cucumber:cucumber-junit-platform-engine")
    testImplementation("org.junit.platform:junit-platform-suite")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")

    androidTestImplementation("io.cucumber:cucumber-android:7.19.0")
    androidTestImplementation("io.cucumber:cucumber-picocontainer:7.34.9")   // the Cucumber-JVM line Cucumber-Android is built on
}
