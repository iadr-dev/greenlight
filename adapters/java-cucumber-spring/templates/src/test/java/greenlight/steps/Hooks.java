package greenlight.steps;

import greenlight.drivers.World;
import io.cucumber.java.After;
import io.cucumber.java.Before;
import io.cucumber.java.Scenario;

/** Per-scenario set-up and clean-up. */
public class Hooks {
    private final World world;

    public Hooks(World world) {
        this.world = world;
    }

    @Before
    public void begin(Scenario scenario) {
        world.begin(scenario.getSourceTagNames());
    }

    @After
    public void end() {
        if (world.seams != null) {
            world.seams.reset();
        }
    }
}
