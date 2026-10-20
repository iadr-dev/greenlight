package greenlight.drivers;

import static io.cucumber.spring.CucumberTestContext.SCOPE_CUCUMBER_GLUE;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeSet;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;

/**
 * Everything one scenario knows. A fresh World is made for every scenario (the Cucumber glue scope, without a scoped
 * proxy so that its fields can be read directly), so nothing leaks between them.
 */
@Component
@Scope(SCOPE_CUCUMBER_GLUE)
public class World {
    /** What the last action did: an API response. */
    public record Outcome(String operation, int status, Object body) {
        public boolean matchesError(String name) {
            Operations.ErrorRule rule = Operations.ERRORS.get(name);
            if (rule == null) {
                throw new Errors.NotMapped("error", name, Operations.ERRORS.keySet());
            }
            boolean statusOk = rule.statuses().isEmpty() || rule.statuses().contains(status);
            boolean textOk = rule.text().isEmpty() || Json.write(body).toLowerCase().contains(rule.text().toLowerCase());
            return statusOk && textOk && (!rule.statuses().isEmpty() || !rule.text().isEmpty());
        }
    }

    public final ApplicationContext context;
    public final MutableClock clock;
    public final Stubs stubs = new Stubs();
    public final Map<String, Map<String, String>> headers = new HashMap<>();   // actor -> auth headers
    public final Map<String, List<Map<String, Object>>> before = new LinkedHashMap<>();
    public final java.util.Set<String> tracked = new TreeSet<>();
    public Outcome outcome;
    public Integer queriesBefore;                                              // statements run before the last action
    public Seams seams;
    private boolean snapshotTaken;
    private MockMvc mvc;

    @Autowired
    public World(ApplicationContext context, MutableClock clock) {
        this.context = context;
        this.clock = clock;
        this.clock.reset();
    }

    /** The MockMvc of the application, built on first use so that a scenario without HTTP needs none. */
    public MockMvc mvc() {
        if (mvc == null) {
            if (!(context instanceof WebApplicationContext web)) {
                throw new Errors.ExpectedMissing("a web application context for the HTTP calls (a servlet web application)");
            }
            mvc = MockMvcBuilders.webAppContextSetup(web).build();
        }
        return mvc;
    }

    /** Called by the Before hook with the scenario's tags. */
    public void begin(java.util.Collection<String> tags) {
        seams = tags.contains("@FEAT-000") ? new SampleSeams(this) : new ProjectSeams(this);
    }

    public void track(String entity) {
        tracked.add(entity);
    }

    /**
     * Called before every action: remember what every tracked entity looked like before the first one, and how many
     * database statements had run before this one.
     */
    public void act() {
        if (!snapshotTaken) {
            for (String entity : tracked) {
                before.put(entity, new ArrayList<>(seams.records(entity)));
            }
            snapshotTaken = true;
        }
        try {
            queriesBefore = seams.queriesExecuted();
        } catch (Errors.ExpectedMissing noCounter) {
            queriesBefore = null;                         // only a scenario that counts needs the seam
        }
    }

    /** The last action ran at most {@code limit} statements (an N+1 problem shows as a count that grows with the rows). */
    public void assertQueriesAtMost(String operation, int limit) {
        if (outcome != null && outcome.operation() != null && !outcome.operation().equals(operation)) {
            throw new AssertionError("the last action was '" + outcome.operation() + "', not '" + operation + "'");
        }
        int total = seams.queriesExecuted();               // raises ExpectedMissing without a counter
        if (queriesBefore == null) {
            throw new AssertionError("no action ran before this check: a When step has to run first");
        }
        int ran = total - queriesBefore;
        if (ran > limit) {
            throw new AssertionError(operation + " ran " + ran + " queries, more than the " + limit
                    + " allowed (a count that grows with the number of records is an N+1 problem)");
        }
    }

    public Outcome last() {
        if (outcome == null) {
            throw new AssertionError("there is no result yet: a When step has to run first");
        }
        return outcome;
    }
}
