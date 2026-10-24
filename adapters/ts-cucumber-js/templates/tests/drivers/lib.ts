// Calling a public function by its logical name; the return value or the error it throws is kept.
import { strict as assert } from 'node:assert';
import { assertEqual, assertSubset } from './compare';
import { NotMapped } from './errors';
import { LIB } from './operations';
import type { GreenlightWorld } from './world';

export async function call(world: GreenlightWorld, operation: string, data: unknown): Promise<void> {
  const mapped = LIB[operation] as ((...args: unknown[]) => unknown) | undefined;
  if (mapped === undefined) {
    throw new NotMapped('library operation', operation, Object.keys(LIB));       // a missing name is a failure, not a result
  }
  try {
    const value = Array.isArray(data) ? await mapped(...data) : await mapped(data);
    world.outcome = { kind: 'lib', body: value, operation, stdout: '', stderr: '' };
  } catch (error) {                                                               // the scenario decides whether this error was wanted
    world.outcome = { kind: 'lib', error, operation, stdout: '', stderr: '' };
  }
}

export function assertResult(world: GreenlightWorld, expected: unknown, exact: boolean): void {
  const outcome = world.last('lib');
  assert.equal(outcome.error, undefined, `the call threw ${outcome.error instanceof Error ? `${outcome.error.constructor.name}: ${outcome.error.message}` : String(outcome.error)}`);
  (exact ? assertEqual : assertSubset)(outcome.body, expected, 'the result');
}

export function assertFails(world: GreenlightWorld, error: string): void {
  const outcome = world.last('lib');
  assert.notEqual(outcome.error, undefined, `the call should fail but returned ${JSON.stringify(outcome.body)}`);
  assert.ok(world.matchesError(outcome, error),
    `the call failed, but not with '${error}': ${outcome.error instanceof Error ? `${outcome.error.constructor.name}: ${outcome.error.message}` : String(outcome.error)}`);
}
