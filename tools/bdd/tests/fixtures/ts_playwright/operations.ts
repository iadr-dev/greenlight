// The contract fixture's logical names: four small pages, the payments dependency, and what to look at on them.
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

export type Target =
  | { role: Parameters<import('@playwright/test').Page['getByRole']>[0]; name?: string }
  | { label: string }
  | { text: string }
  | { testId: string };

const page = (name: string): string => pathToFileURL(resolve('tests/sample', name)).href;

export const PAGES: Record<string, string> = {
  sample: page('index.html'),
  shop: page('shop.html'),
  leak: page('leak.html'),
  clock: page('clock.html'),
  form: page('form.html'),
  orders: '/orders',
};

export const TARGETS: Record<string, Target> = {
  greeting: { testId: 'greeting' },
  'add one button': { role: 'button', name: 'Add one' },
  counter: { testId: 'count' },
  result: { testId: 'result' },
  now: { testId: 'now' },
  'name field': { label: 'Name' },
  'plan field': { label: 'Plan' },
  'agree box': { label: 'Agree' },
  'attachment field': { label: 'Attachment' },
  'save button': { role: 'button', name: 'Save' },
  'remove button': { role: 'button', name: 'Remove' },
  'saved note': { testId: 'saved' },
  secret: { testId: 'secret' },
  steps: { role: 'listitem' },
};

export interface Endpoint {
  method: string;
  url: RegExp;
}

export const DEPENDENCIES: Record<string, Record<string, Endpoint>> = {
  payments: { charge: { method: 'POST', url: /^https:\/\/payments\.test\/v1\/charges$/ } },
};
