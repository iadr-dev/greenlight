// The seams into the system under test. This is the one file of drivers that is specific to the project.
//
// Every method says what it does and fails with ExpectedMissing until the project implements the seam: during the red
// phase that is the right failure. Use the most realistic seam available: the application's own API or a test endpoint
// first, then a domain service, then a repository, then the raw database. Implement a seam as an `async` method (or return
// a promise); the steps wait for it.
import type { HttpClient } from './api';
import type { Clock } from './clock';
import { ExpectedMissing } from './errors';
import type { Stubs } from './stubs';

type Row = Record<string, unknown>;

export class System {
  /** `clock` is the scenario's time and `stubs` its stubbed dependencies: hand them to the application's seams. */
  constructor(readonly clock: Clock, readonly stubs: Stubs) {}

  /** Called once, before the first action of a scenario: start the application (a server on a free port, a database). */
  start(): Promise<void> {
    return Promise.resolve();
  }

  // -- Given ---------------------------------------------------------------------------------
  /** Create `rows` of `entity`. An unknown column is an error. */
  seed(entity: string, _rows: Row[]): Promise<void> {
    return Promise.reject(new ExpectedMissing(`a way to create ${entity} records`));
  }

  /** Sign `actor` in with `role` and return the HTTP headers that prove it. */
  authenticate(_actor: string, role: string): Promise<Record<string, string>> {
    return Promise.reject(new ExpectedMissing(`a way to sign in as ${role}`));
  }

  setFlag(flag: string, _enabled: boolean): Promise<void> {
    return Promise.reject(new ExpectedMissing(`the ${flag} feature flag`));
  }

  /** The scenario's clock is set already (`world.clock`). Override this if the application needs the same time. */
  setTime(_moment: Date): Promise<void> {
    return Promise.resolve();
  }

  // -- When ----------------------------------------------------------------------------------
  /** An HTTP client for the application: `httpClient('http://localhost:3000')` from ./api, or a wrapper around the
   *  framework's in-process test client (supertest, Fastify `inject`, NestJS testing). */
  http(): HttpClient {
    throw new ExpectedMissing('an HTTP client for the application (System.http)');
  }

  deliverEvent(event: string, _payload: unknown): Promise<void> {
    return Promise.reject(new ExpectedMissing(`a way to deliver the ${event} event`));
  }

  runJob(job: string): Promise<void> {
    return Promise.reject(new ExpectedMissing(`the ${job} job`));
  }

  /** Fill in request fields the scenario did not give, for example the id of the order created earlier, so that a step
   *  like `alice calls look up order` needs no id. The default adds nothing. */
  complete(_operation: string, fields: Row): Row {
    return fields;
  }

  // -- Then ----------------------------------------------------------------------------------
  /** Every stored `entity` record, read through a seam that does not change anything. */
  records(entity: string): Promise<Row[]> {
    return Promise.reject(new ExpectedMissing(`a way to read ${entity} records`));
  }

  /** How many database statements have run since the scenario began. Install a `QueryCounter` (see ./queries) on the
   *  application's data access when the system is built, and return its `count`. Only scenarios that check a query
   *  count need this seam. */
  queriesExecuted(): number {
    throw new ExpectedMissing("a counter of the application's database statements");
  }

  /** The payloads of `event` that the application published (a test double of the broker). */
  published(event: string): Promise<unknown[]> {
    return Promise.reject(new ExpectedMissing(`a captured ${event} event`));
  }

  /** Called after every scenario: drop data, close clients. */
  reset(): Promise<void> {
    return Promise.resolve();
  }
}
