// cucumber-js wiring: a fresh world per scenario, and no real network while it runs.
import { After, Before, setWorldConstructor } from '@cucumber/cucumber';
import { blockNetwork, unblockNetwork } from '../drivers/network';
import { GreenlightWorld } from '../drivers/world';

setWorldConstructor(GreenlightWorld);

Before(function () {
  blockNetwork();
});

After(async function (this: GreenlightWorld) {
  try {
    await this.finish();
  } finally {
    unblockNetwork();
  }
});
