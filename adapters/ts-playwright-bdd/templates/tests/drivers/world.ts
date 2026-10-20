// Everything one scenario knows. A fresh World is made for every scenario, so nothing leaks between them.
import { strict as assert } from 'node:assert';
import type { Browser, BrowserContext, Page } from '@playwright/test';
import { Clock } from './clock';
import { type Row } from './compare';
import { Stubs } from './stubs';
import { type Login, System } from './system';

/** An initial value of the browser's local or session storage (the "application state" of a scenario). */
export interface StorageItem {
  storage: 'local' | 'session';
  key: string;
  value: string;
}

export class World {
  readonly system = new System();
  readonly clock = new Clock();
  readonly stubs = new Stubs();
  readonly logins = new Map<string, Login>();
  readonly initialState: StorageItem[] = [];
  readonly tracked = new Set<string>();
  before: Map<string, Row[]> | undefined;
  private readonly contexts = new Map<string, BrowserContext>();
  private readonly pages = new Map<string, Page>();
  private lastActor: string | undefined;

  constructor(private readonly browser: Browser) {}

  /** Called before the first action: remember what every tracked entity looks like. */
  async act(): Promise<void> {
    if (this.before === undefined) {
      this.before = new Map();
      for (const entity of [...this.tracked].sort()) {
        this.before.set(entity, structuredClone(await this.system.records(entity)));
      }
    }
  }

  /** The page of `actor`, in a browser context of their own (signed in as they were told, with the scenario's clock,
   *  stubs and initial state). */
  async page(actor: string): Promise<Page> {
    this.lastActor = actor;
    const known = this.pages.get(actor);
    if (known) {
      return known;
    }
    const login = this.logins.get(actor);
    const context = await this.browser.newContext({ storageState: login?.storageState, extraHTTPHeaders: login?.headers });
    this.contexts.set(actor, context);
    await this.stubs.attach(context);
    await this.clock.attach(context);
    if (this.initialState.length > 0) {
      await context.addInitScript(seedStorage, this.initialState);
    }
    const page = await context.newPage();
    this.pages.set(actor, page);
    return page;
  }

  /** The page of whoever acted last. */
  current(): Page {
    assert.ok(this.lastActor && this.pages.has(this.lastActor), 'no page is open yet: a step like "alice opens the home page" has to come first');
    return this.pages.get(this.lastActor as string) as Page;
  }

  /** Called at the end of every scenario: close the browser contexts, reset the system, fail on refused requests. */
  async finish(): Promise<void> {
    try {
      await Promise.all([...this.contexts.values()].map((context) => context.close()));
    } finally {
      await this.system.reset();
    }
    this.stubs.assertClean();
  }
}

/** Runs in the page before its own scripts, once per browser context: put the initial state into the storage. */
function seedStorage(items: StorageItem[]): void {
  const marker = '__greenlight_seeded';
  if (window.localStorage.getItem(marker)) {
    return;
  }
  for (const { storage, key, value } of items) {
    (storage === 'session' ? window.sessionStorage : window.localStorage).setItem(key, value);
  }
  window.localStorage.setItem(marker, '1');
}
