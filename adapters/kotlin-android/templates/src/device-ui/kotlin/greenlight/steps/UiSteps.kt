package greenlight.steps

import greenlight.drivers.Compare
import greenlight.drivers.Payload
import greenlight.drivers.UiDriver
import greenlight.drivers.World
import io.cucumber.java.After
import io.cucumber.java.en.Given
import io.cucumber.java.en.Then
import io.cucumber.java.en.When

/**
 * The screen instructions of greenlight's step vocabulary (the `ui` profile), bound to [UiDriver]. They run only on a
 * device (this folder is compiled into the instrumented tests), so the scenarios that use them carry the tag `@ui`, which
 * the local JVM run leaves out.
 *
 * Each step carries the id of the instruction it implements in a `// C.…` comment. Steps only call drivers: no resource
 * ids or activity names here. There is one device, so every actor shares it.
 */
class UiSteps(private val world: World) {
    @Given("^the application state is:$") // C.STATE.GLOBAL
    fun stateIs(payload: Payload) {
        world.seams.setApplicationState(Compare.rows(payload.table).associate { it["key"].toString() to it["value"] })
    }

    @When("^([\\w.-]+) opens the (.+) page$") // C.UI.OPEN
    fun opens(actor: String, page: String) {
        world.act()
        UiDriver.open(page)
    }

    @When("^([\\w.-]+) (clicks|fills|selects|uploads|types|toggles|swipes|scrolls) ([^:\\n]+?)$") // C.UI.ACT
    fun acts(actor: String, action: String, target: String) {
        act(action, target, null)
    }

    // The step with data is a method of its own: Cucumber needs one more parameter when a table or doc string follows.
    @When("^([\\w.-]+) (clicks|fills|selects|uploads|types|toggles|swipes|scrolls) ([^:\\n]+?) with:$") // C.UI.ACT
    fun actsWith(actor: String, action: String, target: String, payload: Payload) {
        act(action, target, valueOf(payload.data()))
    }

    /** The value an action carries: the `value` or `direction` cell of a table, its only cell, or a doc string. */
    private fun valueOf(given: Any?): String? {
        val cell = if (given is Map<*, *>) given["value"] ?: given["direction"] ?: given.values.firstOrNull() else given
        return if (cell == null) null else cell.toString()
    }

    private fun act(action: String, target: String, value: String?) {
        world.act()
        UiDriver.act(UiDriver.Action.valueOf(action.uppercase()), target, value)
    }

    @When("^([\\w.-]+) goes back$") // C.UI.BACK
    fun goesBack(actor: String) {
        world.act()
        UiDriver.back()
    }

    @Then("^([\\w.-]+) sees ([^:\\n]+) showing:$") // C.UI.SEE
    fun sees(actor: String, target: String, payload: Payload) {
        UiDriver.assertShows(target, Compare.rows(payload.table), payload.docString)
    }

    @Then("^([\\w.-]+) does not see (.+)$") // C.UI.NOT_SEE
    fun doesNotSee(actor: String, target: String) {
        UiDriver.assertHidden(target)
    }

    @Then("^the application state includes:$") // C.STATE.VERIFY
    fun stateIncludes(payload: Payload) {
        val actual = world.seams.applicationState()
        for (row in Compare.rows(payload.table)) {
            val key = row["key"].toString()
            if (key !in actual) throw AssertionError("the application state has no entry '$key'")
            Compare.assertSubset(actual[key], row["value"], "the application state entry '$key'")
        }
    }

    @After
    fun stopApps() {
        UiDriver.reset()
    }
}
