// Everything one scenario knows. cucumber-js makes a fresh World for every scenario, so nothing leaks between them.
import { strict as assert } from 'node:assert';
import { IWorldOptions, World as CucumberWorld } from '@cucumber/cucumber';
import { Clock } from './clock';
import { type Row } from './compare';
import { ERRORS } from './operations';
import { ExpectedMissing, NotMapped } from './errors';
import { Workspace } from './files';
import { Stubs } from './stubs';
import { System } from './system';

/** What the last action did: an API response, a command, or a library call. */
export interface Outcome {
  kind: 'api' | 'cli' | 'lib';
  status?: number;                 // api
  body?: unknown;                  // api: the parsed body; lib: the returned value
  exitCode?: number;               // cli
  stdout: string;                  // cli
  stderr: string;                  // cli
  error?: unknown;                 // lib: what was thrown
  operation?: string;              // api, lib: the logical name that was called
}

export class GreenlightWorld extends CucumberWorld {
  readonly clock = new Clock();
  readonly stubs = new Stubs();
  readonly system = new System(this.clock, this.stubs);
  readonly workspace = new Workspace();
  private started = false;
  readonly headers = new Map<string, Record<string, string>>();      // actor -> auth headers
  outcome: Outcome | undefined;
  readonly tracked = new Set<string>();                                // entities seeded or verified
  before: Map<string, Row[]> | undefined;
  queriesBefore: number | undefined;                                  // statements run before the last action

  constructor(options: IWorldOptions) {
    super(options);
  }

  /** Called before every action: remember what every tracked entity looked like before the first one, and how many
   *  database statements had run before this one. */
  async act(): Promise<void> {
    if (!this.started) {
      this.started = true;
      await this.system.start();
    }
    if (this.before === undefined) {
      const entities = [...this.tracked].sort((a, b) => a.localeCompare(b));
      const records = await Promise.all(entities.map(async (entity) => [entity, structuredClone(await this.system.records(entity))] as const));
      this.before = new Map(records);
    }
    try {
      this.queriesBefore = this.system.queriesExecuted();
    } catch (error) {
      if (!(error instanceof ExpectedMissing)) {
        throw error;
      }
      this.queriesBefore = undefined;                                  // only a scenario that counts needs the seam
    }
  }

  /** The last action ran at most `limit` statements (an N+1 problem shows as a count that grows with the rows). */
  assertQueriesAtMost(operation: string, limit: number): void {
    const last = this.outcome?.operation;
    assert.ok(last === undefined || last === operation, `the last action was '${last}', not '${operation}'`);
    const total = this.system.queriesExecuted();                      // fails as expected without a counter
    assert.ok(this.queriesBefore !== undefined, 'no action ran before this check: a When step has to run first');
    const ran = total - this.queriesBefore;
    assert.ok(ran <= limit, `${operation} ran ${ran} queries, more than the ${limit} allowed (a count that grows with the number of records is an N+1 problem)`);
  }

  last(kind: Outcome['kind']): Outcome {
    assert.ok(this.outcome, `there is no result yet: a When step (${kind}) has to run first`);
    assert.equal(this.outcome.kind, kind, `the last action was ${this.outcome.kind}, not ${kind}`);
    return this.outcome;
  }

  /** Does the last outcome match the logical error `name`? An error name with no rule is a defect of the test. */
  matchesError(outcome: Outcome, name: string): boolean {
    const rule = ERRORS[name];
    if (rule === undefined) {
      throw new NotMapped('error', name, Object.keys(ERRORS));
    }
    const text = [outcome.body, outcome.stderr, outcome.stdout, outcome.error instanceof Error ? outcome.error.message : outcome.error]
      .filter((part) => part !== undefined && part !== '' && part !== null)
      .map((part) => (typeof part === 'string' ? part : JSON.stringify(part)))
      .join(' ');
    const checks = [
      !rule.statuses || (outcome.status !== undefined && rule.statuses.includes(outcome.status)),
      !rule.exception || (outcome.error instanceof Error && outcome.error.constructor.name === rule.exception),
      rule.exitCode === undefined || outcome.exitCode === rule.exitCode,
      !rule.text || text.toLowerCase().includes(rule.text.toLowerCase()),
    ];
    const anyRule = Boolean(rule.statuses?.length) || Boolean(rule.exception) || rule.exitCode !== undefined || Boolean(rule.text);
    return anyRule && checks.every(Boolean);
  }

  async finish(): Promise<void> {
    try {
      await this.system.reset();
    } finally {
      this.workspace.remove();
    }
  }
}
