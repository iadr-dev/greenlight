package greenlight;

import static io.cucumber.junit.platform.engine.Constants.GLUE_PROPERTY_NAME;

import org.junit.platform.suite.api.ConfigurationParameter;
import org.junit.platform.suite.api.IncludeEngines;
import org.junit.platform.suite.api.SelectClasspathResource;
import org.junit.platform.suite.api.Suite;

/**
 * Runs the feature files. Which features run is decided from outside with Cucumber's own settings, for example
 * {@code -Dcucumber.filter.tags=@FEAT-007} and {@code -Dcucumber.plugin=junit:report.xml} (what {@code bdd run} passes).
 */
@Suite
@IncludeEngines("cucumber")
@SelectClasspathResource("features")
@ConfigurationParameter(key = GLUE_PROPERTY_NAME, value = "greenlight")
public class RunCucumberTest {
}
