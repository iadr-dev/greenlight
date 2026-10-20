// The one fixture the core steps use: a World that exists for exactly one scenario.
import { test as base } from 'playwright-bdd';
import { World } from '../drivers/world';

export const test = base.extend<{ world: World }>({
  world: async ({ browser }, use) => {
    const world = new World(browser);
    try {
      await use(world);
    } finally {
      await world.finish();
    }
  },
});
