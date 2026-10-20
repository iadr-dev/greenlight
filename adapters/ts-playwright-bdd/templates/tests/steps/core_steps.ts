// The core instructions of greenlight's step vocabulary, bound to the drivers.
//
// Each step carries the id of the instruction it implements in a `// C.…` comment; the adapter's contract test checks
// that every instruction of the declared profiles is present. Steps only call drivers: no URLs, no selectors, no SQL
// here. Project-specific steps that compose these live in their own module under tests/steps.
import { strict as assert } from 'node:assert';
import { createBdd, type DataTable } from 'playwright-bdd';
import { assertEqual, assertSubset, payload, rows, sortKey, type Data } from '../drivers/compare';
import * as ui from '../drivers/ui';
import './parameters';
import { test } from './fixtures';

const { Given, When, Then } = createBdd(test);

// -- Given -----------------------------------------------------------------------------------------------------------
Given('the following {entity} exist:', async ({ world }, entity: string, table: DataTable) => { // C.ENTITY.SEED
  world.tracked.add(entity);
  await world.system.seed(entity, rows(table));
});

Given('{actor} is signed in as {role}', async ({ world }, actor: string, role: string) => { // C.ACTOR.AUTH
  world.logins.set(actor, await world.system.authenticate(actor, role));
});

Given('the current time is {datetime}', async ({ world }, moment: string) => { // C.CLOCK.SET
  await world.system.setTime(await world.clock.set(moment));
});

Given('{dependency} responds to {operation} with:', async ({ world }, dependency: string, operation: string, data: Data) => { // C.STUB.RESPOND
  world.stubs.respond(dependency, operation, payload(data));
});

Given('the {flag} feature flag is {state}', async ({ world }, flag: string, state: string) => { // C.FLAG.SET
  await world.system.setFlag(flag, state === 'on');
});

Given('the application state is:', async ({ world }, table: DataTable) => { // C.STATE.GLOBAL
  world.initialState.push(...ui.storageItems(table));
});

// -- When ------------------------------------------------------------------------------------------------------------
When('{actor} opens the {page} page', async ({ world }, actor: string, page: string) => { // C.UI.OPEN
  await world.act();
  await ui.open(world, actor, page);
});

When('{actor} {action} {target}', async ({ world }, actor: string, action: string, target: string) => { // C.UI.ACT
  await world.act();
  await ui.act(world, actor, action as ui.Action, target, undefined);
});

When('{actor} {action} {target} with:', async ({ world }, actor: string, action: string, target: string, data: Data) => { // C.UI.ACT
  await world.act();
  await ui.act(world, actor, action as ui.Action, target, data);
});

When('the {event} event is received with:', async ({ world }, event: string, data: Data) => { // C.EVENT.RECEIVE
  await world.act();
  await world.system.deliverEvent(event, payload(data));
});

When('the {job} job runs', async ({ world }, job: string) => { // C.JOB.RUN
  await world.act();
  await world.system.runJob(job);
});

When('{duration} passes', async ({ world }, duration: string) => { // C.CLOCK.ADVANCE
  await world.system.setTime(await world.clock.advance(duration));
});

// -- Then ------------------------------------------------------------------------------------------------------------
Then('{actor} sees {target} showing:', async ({ world }, actor: string, target: string, data: Data) => { // C.UI.SEE
  await ui.assertShows(world, actor, target, data);
});

Then('{actor} does not see {target}', async ({ world }, actor: string, target: string) => { // C.UI.NOT_SEE
  await ui.assertHidden(world, actor, target);
});

Then('the application state includes:', async ({ world }, table: DataTable) => { // C.STATE.VERIFY
  await ui.assertState(world, table);
});

Then('the {entity} records {mode}:', async ({ world }, entity: string, mode: string, table: DataTable) => { // C.ENTITY.VERIFY
  const actual = await world.system.records(entity);
  const expected = rows(table);
  if (mode === 'include') {
    assertSubset(actual, expected, `the ${entity} records`);
  } else {
    assertEqual([...actual].sort(byKey), [...expected].sort(byKey), `the ${entity} records`);
  }
});

Then('no {entity} records changed', async ({ world }, entity: string) => { // C.ENTITY.UNCHANGED
  const before = world.before?.get(entity);
  assert.ok(before !== undefined, `${entity} records were not tracked: seed them in a Given step (the following ${entity} exist:) so that their state can be compared`);
  assertEqual(await world.system.records(entity), before, `the ${entity} records`);
});

Then('the {event} event is published with:', async ({ world }, event: string, data: Data) => { // C.EVENT.PUBLISHED
  assertSubset(await world.system.published(event), [payload(data)], `the ${event} events`);
});

Then('{dependency} received {operation} with:', async ({ world }, dependency: string, operation: string, data: Data) => { // C.STUB.CALLED
  world.stubs.assertReceived(dependency, operation, payload(data));
});

function byKey(a: unknown, b: unknown): number {
  return sortKey(a).localeCompare(sortKey(b));
}
