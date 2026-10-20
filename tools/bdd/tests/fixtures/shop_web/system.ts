// The seams of the shop-web reference app: its own test endpoints (enabled by SHOP_TEST_ENDPOINTS) for signing in,
// seeding and reading records. Everything else a scenario needs goes through the pages.
import type { BrowserContextOptions } from '@playwright/test';
import { ExpectedMissing } from './errors';

type Row = Record<string, unknown>;

export interface Login {
  storageState?: BrowserContextOptions['storageState'];
  headers?: Record<string, string>;
}

const BASE = 'http://127.0.0.1:3107';

async function call(path: string, body?: unknown): Promise<unknown> {
  const response = await fetch(`${BASE}${path}`, body === undefined ? {} : {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`status ${response.status} for ${path}`);
  }
  return response.json();
}

export class System {
  baseUrl(): string {
    return BASE;
  }

  async seed(entity: string, rows: Row[]): Promise<void> {
    await call('/api/test/seed', { entity, rows });
  }

  async authenticate(actor: string, _role: string): Promise<Login> {
    const cookie = (await call('/api/test/session', { actor })) as { name: string; value: string };
    return {
      storageState: {
        cookies: [{ name: cookie.name, value: cookie.value, domain: '127.0.0.1', path: '/', expires: -1, httpOnly: true, secure: false, sameSite: 'Lax' }],
        origins: [],
      },
    };
  }

  setFlag(flag: string, _enabled: boolean): Promise<void> {
    return Promise.reject(new ExpectedMissing(`the ${flag} feature flag`));
  }

  setTime(_moment: Date): Promise<void> {
    return Promise.resolve();
  }

  deliverEvent(event: string, _payload: unknown): Promise<void> {
    return Promise.reject(new ExpectedMissing(`a way to deliver the ${event} event`));
  }

  runJob(job: string): Promise<void> {
    return Promise.reject(new ExpectedMissing(`the ${job} job`));
  }

  async records(entity: string): Promise<Row[]> {
    return (await call(`/api/test/records?entity=${encodeURIComponent(entity.replaceAll(' ', '-'))}`)) as Row[];
  }

  published(event: string): Promise<unknown[]> {
    return Promise.reject(new ExpectedMissing(`a captured ${event} event`));
  }

  async reset(): Promise<void> {
    await call('/api/test/reset', {});
  }
}
