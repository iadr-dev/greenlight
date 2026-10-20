// Applied from the module's build file with: apply(from = "greenlight.gradle.kts")
//
// `bdd run` hands Cucumber its settings as Gradle properties (-Pcucumber.filter.tags=@FEAT-007,
// -Pcucumber.plugin=junit:report.xml). Gradle does not pass properties to the test JVM by itself, so this script does,
// and makes every run really run the tests instead of reusing an earlier result.
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    outputs.upToDateWhen { false }
    project.properties
        .filterKeys { it.startsWith("cucumber.") }
        .forEach { (name, value) -> systemProperty(name, value.toString()) }
    testLogging {
        events("failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
