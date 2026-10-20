package greenlight.steps

import greenlight.drivers.Compare
import greenlight.drivers.LibDriver
import greenlight.drivers.Payload
import greenlight.drivers.World
import io.cucumber.datatable.DataTable
import io.cucumber.java.en.Given
import io.cucumber.java.en.Then
import io.cucumber.java.en.When

/**
 * The core instructions of greenlight's step vocabulary, bound to the drivers.
 *
 * Each step carries the id of the instruction it implements in a `// C.…` comment; the adapter's contract test checks
 * that every instruction of the declared profiles is present. Steps only call drivers: no class names, no SQL here.
 * Project-specific steps that compose these live in their own class under this package.
 */
class CoreSteps(private val world: World) {
    // -- Given ----------------------------------------------------------------------------------------------------
    @Given("^the following (.+) exist:$") // C.ENTITY.SEED
    fun entitiesExist(entity: String, table: DataTable) {
        world.track(entity)
        world.seams.seed(entity, Compare.rows(table))
    }

    @Given("^(.+) is signed in as (.+)$") // C.ACTOR.AUTH
    fun actorSignedIn(actor: String, role: String) {
        world.headers[actor] = world.seams.authenticate(actor, role)
    }

    @Given("^the current time is (.+)$") // C.CLOCK.SET
    fun timeIs(moment: String) {
        world.clock.set(moment)
    }

    @Given("^(.+) responds to (.+) with:$") // C.STUB.RESPOND
    fun dependencyResponds(dependency: String, operation: String, payload: Payload) {
        world.stubs.respond(dependency, operation, payload.data())
    }

    @Given("^the (.+) feature flag is (on|off)$") // C.FLAG.SET
    fun flagIs(flag: String, state: String) {
        world.seams.setFlag(flag, state == "on")
    }

    // -- When -----------------------------------------------------------------------------------------------------
    @When("^(.+) is called with:$") // C.LIB.CALL
    fun libCall(operation: String, payload: Payload) {
        world.act()
        LibDriver.call(world, operation, payload.data())
    }

    @When("^the (.+) event is received with:$") // C.EVENT.RECEIVE
    fun eventReceived(event: String, payload: Payload) {
        world.act()
        world.seams.deliverEvent(event, payload.data())
    }

    @When("^the (.+) job runs$") // C.JOB.RUN
    fun jobRuns(job: String) {
        world.act()
        world.seams.runJob(job)
    }

    @When("^(.+) passes$") // C.CLOCK.ADVANCE
    fun timePasses(duration: String) {
        world.clock.advance(duration)
    }

    // -- Then -----------------------------------------------------------------------------------------------------
    @Then("^the (.+) records (are|include):$") // C.ENTITY.VERIFY
    fun recordsVerified(entity: String, mode: String, table: DataTable) {
        val actual = world.seams.records(entity)
        val expected = Compare.rows(table)
        if (mode == "include") {
            Compare.assertSubset(actual, expected, "the $entity records")
        } else {
            Compare.assertEqual(actual.sortedWith(Compare.byContent), expected.sortedWith(Compare.byContent), "the $entity records")
        }
    }

    @Then("^no (.+) records changed$") // C.ENTITY.UNCHANGED
    fun recordsUnchanged(entity: String) {
        val before = world.before[entity] ?: throw AssertionError(
            "$entity records were not tracked: seed them in a Given step (the following $entity exist:) so that their " +
                "state can be compared",
        )
        Compare.assertEqual(world.seams.records(entity), before, "the $entity records")
    }

    @Then("^(.+) ran at most (\\d+) queries$") // C.QUERY.COUNT
    fun queriesAtMost(operation: String, count: Int) {
        world.assertQueriesAtMost(operation, count)
    }

    @Then("^the (.+) event is published with:$") // C.EVENT.PUBLISHED
    fun eventPublished(event: String, payload: Payload) {
        Compare.assertSubset(world.seams.published(event), listOf(payload.data()), "the $event events")
    }

    @Then("^(.+) received (.+) with:$") // C.STUB.CALLED
    fun dependencyReceived(dependency: String, operation: String, payload: Payload) {
        world.stubs.assertReceived(dependency, operation, payload.data())
    }

    @Then("^the result is:$") // C.LIB.RESULT
    fun resultIs(payload: Payload) {
        LibDriver.assertResult(world, payload.data(), exact = true)
    }

    @Then("^the result includes:$") // C.LIB.RESULT
    fun resultIncludes(payload: Payload) {
        LibDriver.assertResult(world, payload.data(), exact = false)
    }

    @Then("^the call fails with (.+)$") // C.LIB.RESULT
    fun callFails(error: String) {
        LibDriver.assertFails(world, error)
    }
}
