package greenlight.steps;

import greenlight.drivers.ApiDriver;
import greenlight.drivers.Compare;
import greenlight.drivers.Payload;
import greenlight.drivers.World;
import io.cucumber.datatable.DataTable;
import io.cucumber.java.en.Given;
import io.cucumber.java.en.Then;
import io.cucumber.java.en.When;
import java.util.Comparator;
import java.util.List;
import java.util.Map;

/**
 * The core instructions of greenlight's step vocabulary, bound to the drivers.
 *
 * <p>Each step carries the id of the instruction it implements in a {@code // C.…} comment; the adapter's contract
 * test checks that every instruction of the declared profiles is present. Steps only call drivers: no paths, no class
 * names, no SQL here. Project-specific steps that compose these live in their own class under this package.
 */
public class CoreSteps {
    private final World world;

    public CoreSteps(World world) {
        this.world = world;
    }

    // -- Given ----------------------------------------------------------------------------------------------------
    @Given("^the following (.+) exist:$") // C.ENTITY.SEED
    public void entitiesExist(String entity, DataTable table) {
        world.track(entity);
        world.seams.seed(entity, Compare.rows(table));
    }

    @Given("^(.+) is signed in as (.+)$") // C.ACTOR.AUTH
    public void actorSignedIn(String actor, String role) {
        world.headers.put(actor, world.seams.authenticate(actor, role));
    }

    @Given("^the current time is (.+)$") // C.CLOCK.SET
    public void timeIs(String moment) {
        world.clock.set(moment);
    }

    @Given("^(.+) responds to (.+) with:$") // C.STUB.RESPOND
    public void dependencyResponds(String dependency, String operation, Payload payload) {
        world.stubs.respond(dependency, operation, payload.data());
    }

    @Given("^the (.+) feature flag is (on|off)$") // C.FLAG.SET
    public void flagIs(String flag, String state) {
        world.seams.setFlag(flag, "on".equals(state));
    }

    // -- When -----------------------------------------------------------------------------------------------------
    @When("^(.+?) calls (.+?)(?<! with:)$") // C.API.CALL
    public void apiCall(String actor, String operation) {
        world.act();
        ApiDriver.call(world, actor, operation, null);
    }

    @When("^(.+?) calls (.+?) with:$") // C.API.CALL
    public void apiCallWith(String actor, String operation, Payload payload) {
        world.act();
        ApiDriver.call(world, actor, operation, payload.data());
    }

    @When("^the (.+) event is received with:$") // C.EVENT.RECEIVE
    public void eventReceived(String event, Payload payload) {
        world.act();
        world.seams.deliverEvent(event, payload.data());
    }

    @When("^the (.+) job runs$") // C.JOB.RUN
    public void jobRuns(String job) {
        world.act();
        world.seams.runJob(job);
    }

    @When("^(.+) passes$") // C.CLOCK.ADVANCE
    public void timePasses(String duration) {
        world.clock.advance(duration);
    }

    // -- Then -----------------------------------------------------------------------------------------------------
    @Then("^the request succeeds$") // C.API.STATUS
    public void requestSucceeds() {
        ApiDriver.assertSucceeds(world);
    }

    @Then("^the request is rejected with (.+)$") // C.API.STATUS
    public void requestRejected(String error) {
        ApiDriver.assertRejected(world, error);
    }

    @Then("^the response contains:$") // C.API.BODY
    public void responseContains(Payload payload) {
        Compare.assertSubset(world.last().body(), payload.data(), "the response");
    }

    @Then("^the (.+) records (are|include):$") // C.ENTITY.VERIFY
    public void recordsVerified(String entity, String mode, DataTable table) {
        List<Map<String, Object>> actual = world.seams.records(entity);
        List<Map<String, Object>> expected = Compare.rows(table);
        if ("include".equals(mode)) {
            Compare.assertSubset(actual, expected, "the " + entity + " records");
        } else {
            Comparator<Map<String, Object>> order = Compare.byContent();
            Compare.assertEqual(actual.stream().sorted(order).toList(), expected.stream().sorted(order).toList(),
                    "the " + entity + " records");
        }
    }

    @Then("^no (.+) records changed$") // C.ENTITY.UNCHANGED
    public void recordsUnchanged(String entity) {
        if (!world.before.containsKey(entity)) {
            throw new AssertionError(entity + " records were not tracked: seed them in a Given step (the following "
                    + entity + " exist:) so that their state can be compared");
        }
        Compare.assertEqual(world.seams.records(entity), world.before.get(entity), "the " + entity + " records");
    }

    @Then("^(.+) ran at most (\\d+) queries$") // C.QUERY.COUNT
    public void queriesAtMost(String operation, int count) {
        world.assertQueriesAtMost(operation, count);
    }

    @Then("^the (.+) event is published with:$") // C.EVENT.PUBLISHED
    public void eventPublished(String event, Payload payload) {
        Compare.assertSubset(world.seams.published(event), List.of(payload.data()), "the " + event + " events");
    }

    @Then("^(.+) received (.+) with:$") // C.STUB.CALLED
    public void dependencyReceived(String dependency, String operation, Payload payload) {
        world.stubs.assertReceived(dependency, operation, payload.data());
    }
}
