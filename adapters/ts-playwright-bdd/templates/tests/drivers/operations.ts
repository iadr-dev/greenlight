// Logical names (as written in the features and the glossary) -> what they mean in this application.
// This is the one place where URLs, selectors and external hosts appear; features never contain them.
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

/** How to find an element. Prefer what a user perceives (role and name, label, text); a test id is the fallback. */
export type Target =
  | { role: Parameters<import('@playwright/test').Page['getByRole']>[0]; name?: string }
  | { label: string }
  | { text: string }
  | { testId: string };

/** A page: a path under the application's base URL (see System.baseUrl), or a complete URL. */
export const PAGES: Record<string, string> = {
  // 'orders': '/orders',
  sample: pathToFileURL(resolve('tests/sample/index.html')).href,
};

export const TARGETS: Record<string, Target> = {
  // 'checkout button': { role: 'button', name: 'Check out' },
  greeting: { testId: 'greeting' },
  'add one button': { role: 'button', name: 'Add one' },
  counter: { testId: 'count' },
};

/** An external HTTP dependency: which requests belong to which logical operation. Only these can be stubbed. */
export interface Endpoint {
  method: string;
  url: RegExp;
}

export const DEPENDENCIES: Record<string, Record<string, Endpoint>> = {
  // payments: { charge: { method: 'POST', url: /\/v1\/charges$/ } },
};
