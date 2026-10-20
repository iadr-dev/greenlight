package greenlight.drivers;

import java.util.List;
import java.util.Map;

/**
 * The seams into the system under test. {@link ProjectSeams} (the one file of drivers that is specific to the project)
 * overrides what the project has.
 *
 * <p>Every method says what it does and raises {@link Errors.ExpectedMissing} until the project implements the seam:
 * during the red phase that is the right failure. Use the most realistic seam available: the API first, then a domain
 * service, then a repository, then the raw database.
 */
public class Seams {
    protected final World world;

    public Seams(World world) {
        this.world = world;
    }

    // -- Given ------------------------------------------------------------------------------------------------
    /** Create {@code rows} of {@code entity}. An unknown column is an error. */
    public void seed(String entity, List<Map<String, Object>> rows) {
        throw new Errors.ExpectedMissing("a way to create " + entity + " records");
    }

    /** Sign {@code actor} in with {@code role} and return the HTTP headers that prove it. */
    public Map<String, String> authenticate(String actor, String role) {
        throw new Errors.ExpectedMissing("a way to sign in as " + role);
    }

    public void setFlag(String flag, boolean enabled) {
        throw new Errors.ExpectedMissing("the " + flag + " feature flag");
    }

    // -- When -------------------------------------------------------------------------------------------------
    public void deliverEvent(String event, Object payload) {
        throw new Errors.ExpectedMissing("a way to deliver the " + event + " event");
    }

    public void runJob(String job) {
        throw new Errors.ExpectedMissing("the " + job + " job");
    }

    /**
     * Fill in request fields the scenario did not give, for example the id of the order created earlier, so a step like
     * {@code alice calls look up order} needs no id. The default adds nothing.
     */
    public Map<String, Object> complete(String operation, Map<String, Object> fields) {
        return fields;
    }

    // -- Then -------------------------------------------------------------------------------------------------
    /** Every stored {@code entity} record, read through a seam that does not change anything. */
    public List<Map<String, Object>> records(String entity) {
        throw new Errors.ExpectedMissing("a way to read " + entity + " records");
    }

    /**
     * How many database statements have run so far, counted by the {@link QueryCounter} that GreenlightTestConfig puts
     * around the application's data sources. Without a data source there is nothing to count, which is an expected
     * failure. Only scenarios that check a query count need this seam.
     */
    public int queriesExecuted() {
        QueryCounter counter = QueryCounter.shared();
        if (!counter.attached()) {
            throw new Errors.ExpectedMissing("a data source whose statements can be counted");
        }
        return counter.count();
    }

    /** The payloads of {@code event} that the application published (a test double of the broker). */
    public List<Object> published(String event) {
        throw new Errors.ExpectedMissing("a captured " + event + " event");
    }

    /** Called after every scenario: drop data, close clients. */
    public void reset() {
        // nothing to clean by default
    }
}
