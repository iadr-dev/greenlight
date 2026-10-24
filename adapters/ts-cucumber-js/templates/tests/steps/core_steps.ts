// The core instructions of greenlight's step vocabulary, bound to the drivers.
//
// Each step carries the id of the instruction it implements in a `// C.…` comment; the adapter's contract test checks that
// every instruction of the declared profiles is present. Steps only call drivers: no URLs, no paths, no SQL here.
// Project-specific steps that compose these live in their own module under tests/steps.
import { strict as assert } from 'node:assert';
import { Given, Then, When, type DataTable } from '@cucumber/cucumber';
import * as api from '../drivers/api';
import * as cli from '../drivers/cli';
import { assertEqual, assertSubset, assertTextContains, payload, rows, sortKey, textOf, type Data } from '../drivers/compare';
import * as lib from '../drivers/lib';
import type { GreenlightWorld } from '../drivers/world';
import './support';

type World = GreenlightWorld;

// cucumber-js requires a step function to declare exactly as many parameters as it is given (the words matched, then the doc
// string or table), so a phrase that may or may not carry data is two steps: one ending in "with:" and one that does not.

// -- Given -----------------------------------------------------------------------------------------------------------
Given(/^the following (.+) exist:$/, async function (this: World, entity: string, table: DataTable) { // C.ENTITY.SEED
  this.tracked.add(entity);
  await this.system.seed(entity, rows(table));
});

Given(/^(.+) is signed in as (.+)$/, async function (this: World, actor: string, role: string) { // C.ACTOR.AUTH
  this.headers.set(actor, await this.system.authenticate(actor, role));
});

Given(/^the current time is (.+)$/, async function (this: World, moment: string) { // C.CLOCK.SET
  await this.system.setTime(this.clock.set(moment));
});

Given(/^(.+) responds to (.+) with:$/, function (this: World, dependency: string, operation: string, data: Data) { // C.STUB.RESPOND
  this.stubs.respond(dependency, operation, payload(data));
});

Given(/^the (.+) feature flag is (on|off)$/, async function (this: World, flag: string, state: string) { // C.FLAG.SET
  await this.system.setFlag(flag, state === 'on');
});

Given(/^the input file (.+) contains:$/, function (this: World, file: string, data: Data) { // C.FILE.GIVEN
  this.workspace.write(file, textOf(data));
});

// -- When ------------------------------------------------------------------------------------------------------------
When(/^the (.+) event is received with:$/, async function (this: World, event: string, data: Data) { // C.EVENT.RECEIVE
  await this.act();
  await this.system.deliverEvent(event, payload(data));
});

When(/^the (.+) job runs$/, async function (this: World, job: string) { // C.JOB.RUN
  await this.act();
  await this.system.runJob(job);
});

When(/^(.+) is called with:$/, async function (this: World, operation: string, data: Data) { // C.LIB.CALL
  await this.act();
  await lib.call(this, operation, payload(data));
});

When(/^(.+) calls (.+) with:$/, async function (this: World, actor: string, operation: string, data: Data) { // C.API.CALL
  await this.act();
  await api.call(this, actor, operation, payload(data));
});

When(/^(.+) calls (.+?)(?<! with:)$/, async function (this: World, actor: string, operation: string) { // C.API.CALL
  await this.act();
  await api.call(this, actor, operation, undefined);
});

When(/^(.+) runs (.+) with:$/, async function (this: World, _actor: string, command: string, table: DataTable) { // C.CLI.RUN
  await this.act();
  cli.run(this, command, table);
});

When(/^(.+) runs (.+?)(?<! with:)$/, async function (this: World, _actor: string, command: string) { // C.CLI.RUN
  await this.act();
  cli.run(this, command, undefined);
});

When(/^(.+) passes$/, async function (this: World, duration: string) { // C.CLOCK.ADVANCE
  await this.system.setTime(this.clock.advance(duration));
});

// -- Then ------------------------------------------------------------------------------------------------------------
Then(/^the request succeeds$/, function (this: World) { // C.API.STATUS
  api.assertSucceeds(this);
});

Then(/^the request is rejected with (.+)$/, function (this: World, error: string) { // C.API.STATUS
  api.assertRejected(this, error);
});

Then(/^the response contains:$/, function (this: World, data: Data) { // C.API.BODY
  assertSubset(this.last('api').body, payload(data), 'the response');
});

Then(/^the (.+) records (are|include):$/, async function (this: World, entity: string, mode: string, table: DataTable) { // C.ENTITY.VERIFY
  const actual = await this.system.records(entity);
  const expected = rows(table);
  if (mode === 'include') {
    assertSubset(actual, expected, `the ${entity} records`);
  } else {
    assertEqual([...actual].sort(byKey), [...expected].sort(byKey), `the ${entity} records`);
  }
});

Then(/^no (.+) records changed$/, async function (this: World, entity: string) { // C.ENTITY.UNCHANGED
  const before = this.before?.get(entity);
  assert.ok(before !== undefined, `${entity} records were not tracked: seed them in a Given step (the following ${entity} exist:) so that their state can be compared`);
  assertEqual(await this.system.records(entity), before, `the ${entity} records`);
});

Then(/^(.+) ran at most (\d+) queries$/, function (this: World, operation: string, count: string) { // C.QUERY.COUNT
  this.assertQueriesAtMost(operation, Number(count));
});

Then(/^the (.+) event is published with:$/, async function (this: World, event: string, data: Data) { // C.EVENT.PUBLISHED
  assertSubset(await this.system.published(event), [payload(data)], `the ${event} events`);
});

Then(/^(.+) received (.+) with:$/, function (this: World, dependency: string, operation: string, data: Data) { // C.STUB.CALLED
  this.stubs.assertReceived(dependency, operation, payload(data));
});

Then(/^the command succeeds$/, function (this: World) { // C.CLI.RESULT
  cli.assertSucceeds(this);
});

Then(/^the command fails with (.+)$/, function (this: World, error: string) { // C.CLI.RESULT
  cli.assertFails(this, error);
});

Then(/^the (stdout|stderr) output contains:$/, function (this: World, stream: string, data: Data) { // C.OUTPUT.CONTAINS
  const outcome = this.last('cli');
  assertTextContains(stream === 'stdout' ? outcome.stdout : outcome.stderr, textOf(data), `the ${stream} output`);
});

Then(/^the output file (.+) contains:$/, function (this: World, file: string, data: Data) { // C.FILE.VERIFY
  this.workspace.assertContains(file, textOf(data));
});

Then(/^the result is:$/, function (this: World, data: Data) { // C.LIB.RESULT
  lib.assertResult(this, payload(data), true);
});

Then(/^the result includes:$/, function (this: World, data: Data) { // C.LIB.RESULT
  lib.assertResult(this, payload(data), false);
});

Then(/^the call fails with (.+)$/, function (this: World, error: string) { // C.LIB.RESULT
  lib.assertFails(this, error);
});

function byKey(a: unknown, b: unknown): number {
  return sortKey(a).localeCompare(sortKey(b));
}
