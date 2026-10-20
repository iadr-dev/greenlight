package greenlight;

import greenlight.drivers.MutableClock;
import greenlight.drivers.NetworkGuard;
import greenlight.drivers.QueryCounter;
import javax.sql.DataSource;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

/**
 * What the tests add to the application context: the injected clock, a counter around every data source, the drivers
 * themselves, and the guard against real outbound HTTP connections.
 */
@Configuration
@ComponentScan("greenlight.drivers")
public class GreenlightTestConfig {

    /** Replaces the application's {@code java.time.Clock} in tests; code that reads time through a Clock follows the scenario. */
    @Bean
    @Primary
    public MutableClock greenlightClock() {
        return new MutableClock();
    }

    @Bean
    public static BeanPostProcessor countingDataSources() {
        NetworkGuard.install();
        return new BeanPostProcessor() {
            @Override
            public Object postProcessAfterInitialization(Object bean, String beanName) {
                return bean instanceof DataSource dataSource ? QueryCounter.shared().wrap(dataSource) : bean;
            }
        };
    }
}
