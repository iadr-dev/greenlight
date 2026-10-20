package greenlight;

import io.cucumber.spring.CucumberContextConfiguration;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * Starts the application once for all scenarios. Replace SampleApplication with the project's own
 * {@code @SpringBootApplication} class, and keep GreenlightTestConfig.
 */
@CucumberContextConfiguration
@SpringBootTest(classes = {SampleApplication.class, GreenlightTestConfig.class})
public class GreenlightSpring {
}
