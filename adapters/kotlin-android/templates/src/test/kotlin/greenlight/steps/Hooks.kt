package greenlight.steps

import greenlight.drivers.World
import io.cucumber.java.After
import io.cucumber.java.Before
import io.cucumber.java.Scenario

/** Per-scenario set-up and clean-up. */
class Hooks(private val world: World) {
    @Before
    fun begin(scenario: Scenario) {
        world.begin(scenario.sourceTagNames)
    }

    @After
    fun end() {
        world.seams.reset()
    }
}
