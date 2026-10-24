// Stubbed external dependencies.
//
// Route the application's outbound calls through `world.stubs.call(dependency, operation, request)` (an HTTP client
// wrapper, a gateway interface) or point a mocking library at `respond`. A call the scenario did not stub fails the scenario.
import { strict as assert } from 'node:assert';
import { assertSubset } from './compare';
import { UnstubbedCall } from './errors';

interface Call {
  dependency: string;
  operation: string;
  request: unknown;
}

export class Stubs {
  private readonly responses = new Map<string, unknown>();
  readonly calls: Call[] = [];

  respond(dependency: string, operation: string, response: unknown): void {
    this.responses.set(`${dependency}.${operation}`, response);
  }

  call(dependency: string, operation: string, request?: unknown): unknown {
    this.calls.push({ dependency, operation, request });
    const key = `${dependency}.${operation}`;
    if (!this.responses.has(key)) {
      throw new UnstubbedCall(`${dependency} was asked to ${operation} but the scenario did not stub it`);
    }
    return this.responses.get(key);
  }

  assertReceived(dependency: string, operation: string, expected: unknown): void {
    const requests = this.calls.filter((c) => c.dependency === dependency && c.operation === operation).map((c) => c.request);
    assert.ok(requests.length > 0, `${dependency} never received ${operation}; it received ${JSON.stringify(this.calls.map((c) => [c.dependency, c.operation]))}`);
    if (expected === null || expected === undefined || (Array.isArray(expected) && expected.length === 0)
      || (typeof expected === 'object' && Object.keys(expected as object).length === 0)) {
      return;
    }
    assertSubset(requests, [expected], `the ${operation} requests received by ${dependency}`);
  }
}
