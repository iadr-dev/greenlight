// The seams into the system under test. This is the one file of drivers that is specific to the project.
//
// Every method says what it does and throws ExpectedMissing until the project implements the seam: during the
// red phase that is the right failure. Use the most realistic seam available: the application's own API or a
// test endpoint first, then a domain service, then a repository, then the raw database.
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
  async seed(entity: string, _rows: Row[]): Promise<void> {
    throw new ExpectedMissing(`a way to create ${entity} records`);
  }

  /** Sign `actor` in with `role` and return what the browser needs to be signed in. */
  async authenticate(_actor: string, role: string): Promise<Login> {
    throw new ExpectedMissing(`a way to sign in as ${role}`);
  }

  async setFlag(flag: string, _enabled: boolean): Promise<void> {
    throw new ExpectedMissing(`the ${flag} feature flag`);
  }

  /** The browser's clock is set by the scenario already. Override this if the server needs the same time. */
  async setTime(_moment: Date): Promise<void> {}

  // -- When ----------------------------------------------------------------------------------
  async deliverEvent(event: string, _payload: unknown): Promise<void> {
    throw new ExpectedMissing(`a way to deliver the ${event} event`);
  }

  async runJob(job: string): Promise<void> {
    throw new ExpectedMissing(`the ${job} job`);
  }

  // -- Then ----------------------------------------------------------------------------------
  /** Every stored `entity` record, read through a seam that does not change anything. */
  async records(entity: string): Promise<Row[]> {
    throw new ExpectedMissing(`a way to read ${entity} records`);
  }

  /** The payloads of `event` that the application published (a test double of the broker). */
  async published(event: string): Promise<unknown[]> {
    throw new ExpectedMissing(`a captured ${event} event`);
  }

  /** Called after every scenario: drop data, close clients. */
  async reset(): Promise<void> {}
}
