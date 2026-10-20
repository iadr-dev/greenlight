plugins {
    id("com.android.library") version "9.4.1"
}

apply(from = "greenlight.gradle.kts")

android {
    namespace = "contract"
    compileSdk = 36

    defaultConfig {
        minSdk = 24
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
}
