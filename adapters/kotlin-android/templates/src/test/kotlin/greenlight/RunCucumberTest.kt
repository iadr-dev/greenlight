package greenlight

import io.cucumber.junit.platform.engine.Constants.GLUE_PROPERTY_NAME
import org.junit.platform.suite.api.ConfigurationParameter
import org.junit.platform.suite.api.IncludeEngines
import org.junit.platform.suite.api.SelectClasspathResource
import org.junit.platform.suite.api.Suite

/**
 * Runs the feature files. Which features run is decided from outside with Cucumber's own settings, for example
 * `-Pcucumber.filter.tags=@FEAT-007` and `-Pcucumber.plugin=junit:report.xml` (what `bdd run` passes; greenlight.gradle.kts
 * hands them to the test JVM).
 */
@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "greenlight")
class RunCucumberTest
