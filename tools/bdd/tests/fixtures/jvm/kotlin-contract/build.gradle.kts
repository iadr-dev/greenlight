plugins {
    kotlin("jvm") version "2.4.21"
}

apply(from = "greenlight.gradle.kts")

repositories {
    mavenCentral()
}

dependencyLocking {
    lockAllConfigurations()          // the resolved versions are in gradle.lockfile: a run never picks up a newer one
}

dependencies {
    testImplementation(platform("io.cucumber:cucumber-bom:8.0.4"))
    testImplementation("io.cucumber:cucumber-java")
    testImplementation("io.cucumber:cucumber-picocontainer")
    testImplementation("io.cucumber:cucumber-junit-platform-engine")
    testImplementation("org.junit.platform:junit-platform-suite")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
