// The seams into the system under test. This is the one file of drivers that is specific to the project.
//
// Every method says what it does and fails with ExpectedMissing until the project implements the seam: during the
// red phase that is the right failure. Use the most realistic seam available: the application's own API or a
// test endpoint first, then a domain service, then a repository, then the raw database. Implement a seam as an
// `async` method (or return a promise); the steps wait for it.
import type { BrowserContextOptions } from '@playwright/test';
import { ExpectedMissing } from './errors';

type Row = Record<string, unknown>;

/** What signing an actor in gives the browser: a stored session (cookies, local storage) and/or extra headers. */
export interface Login {
  storageState?: BrowserContextOptions['storageState'];
  headers?: Record<string, string>;
}

export class System {
  // -- Given ---------------------------------------------------------------------------------
  /** The address pages are opened under, such as 'http://localhost:3000'. */
  baseUrl(): string {
    throw new ExpectedMissing('a running application to open pages of (System.baseUrl)');
  }

  /** Create `rows` of `entity`. An unknown column is an error. */
  seed(entity: string, _rows: Row[]): Promise<void> {
    return Promise.reject(new ExpectedMissing(`a way to create ${entity} records`));
  }

  /** Sign `actor` in with `role` and return what the browser needs to be signed in. */
  authenticate(_actor: string, role: string): Promise<Login> {
    return Promise.reject(new ExpectedMissing(`a way to sign in as ${role}`));
  }

  setFlag(flag: string, _enabled: boolean): Promise<void> {
    return Promise.reject(new ExpectedMissing(`the ${flag} feature flag`));
  }

  /** The browser's clock is set by the scenario already. Override this if the server needs the same time. */
  setTime(_moment: Date): Promise<void> {
    return Promise.resolve();
  }

  // -- When ----------------------------------------------------------------------------------
  deliverEvent(event: string, _payload: unknown): Promise<void> {
    return Promise.reject(new ExpectedMissing(`a way to deliver the ${event} event`));
  }

  runJob(job: string): Promise<void> {
    return Promise.reject(new ExpectedMissing(`the ${job} job`));
  }

  // -- Then ----------------------------------------------------------------------------------
  /** Every stored `entity` record, read through a seam that does not change anything. */
  records(entity: string): Promise<Row[]> {
    return Promise.reject(new ExpectedMissing(`a way to read ${entity} records`));
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
