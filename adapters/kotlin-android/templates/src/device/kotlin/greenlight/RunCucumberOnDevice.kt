package greenlight

import io.cucumber.junit.CucumberOptions

/**
 * Runs the same feature files and steps on a device, through Cucumber-Android. This folder is not an Android source set,
 * so the class is built only when the module's build file adds it to the instrumented tests (see the adapter guide,
 * "Running the scenarios on a device"). Which scenarios run is decided from outside, as on the JVM: `bdd run` passes
 * the tag (and, when isolated, the name) as instrumentation arguments.
 */
@CucumberOptions(glue = ["greenlight"], features = ["features"])
class RunCucumberOnDevice
