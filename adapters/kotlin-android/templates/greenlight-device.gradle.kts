// Applied from the module's build file, next to greenlight.gradle.kts, only when the scenarios also run on a device:
//     apply(from = "greenlight-device.gradle.kts")
//
// The same feature files and steps run as instrumented tests through Cucumber-Android. `bdd run` hands the runner its
// selection as instrumentation arguments (-Pandroid.testInstrumentationRunnerArguments.tags=@FEAT-007) and names the file
// the report goes to (-Pgreenlight.report=<file>). Cucumber's own JUnit plugin does not work on Android, so the report is
// the one the Android Gradle Plugin writes for the instrumented run: this script removes the results of an earlier run
// before the tests start, and afterwards copies the new report to the file `bdd run` reads. One device must be connected
// (or chosen with ANDROID_SERIAL): with several, there would be one report per device and no single result.
val greenlightReport = providers.gradleProperty("greenlight.report")
val instrumentedResults = layout.buildDirectory.dir("outputs/androidTest-results/connected")

val greenlightDeviceReport = tasks.register("greenlightDeviceReport") {
    description = "Copies the report of the instrumented run to the file `bdd run` reads."
    onlyIf { greenlightReport.isPresent }
    doLast {
        val reports = instrumentedResults.get().asFile.walkTopDown()
            .filter { it.isFile && it.name.startsWith("TEST-") && it.name.endsWith(".xml") }
            .toList()
        if (reports.size != 1) {
            throw GradleException(
                "expected one instrumented test report under ${instrumentedResults.get().asFile}, found ${reports.size}: " +
                    "connect one device, or choose one with ANDROID_SERIAL"
            )
        }
        reports.single().copyTo(file(greenlightReport.get()), overwrite = true)
    }
}

tasks.matching { it.name.startsWith("connected") && it.name.endsWith("AndroidTest") }.configureEach {
    outputs.upToDateWhen { false }
    doFirst { instrumentedResults.get().asFile.deleteRecursively() }
    finalizedBy(greenlightDeviceReport)
}

// The shared step sources also hold the JUnit Platform suite that runs them on the JVM; on the device Cucumber-Android
// is the runner, so that one class is left out of the instrumented build.
tasks.matching { it.name.startsWith("compile") && it.name.endsWith("AndroidTestKotlin") }.configureEach {
    (this as org.gradle.api.tasks.util.PatternFilterable).exclude("**/greenlight/RunCucumberTest.kt")
}
