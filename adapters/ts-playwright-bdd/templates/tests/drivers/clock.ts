// The scenario's clock. Once a scenario sets the time, every browser context of that scenario runs on a frozen clock
// that only moves when the scenario says time passes. The server's clock is the project's business (System.setTime).
import { strict as assert } from 'node:assert';
import type { BrowserContext } from '@playwright/test';
import { durationMs } from './compare';

export class Clock {
  private moment: Date | undefined;
  private readonly contexts = new Set<BrowserContext>();

  /** Parse an ISO date or date-time ("2026-03-01", "2026-03-01 09:30", "2026-03-01T09:30:00Z"); no zone means UTC. */
  static parse(text: string): Date {
    const iso = text.trim().replace(' ', 'T');
    const moment = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(iso) || !iso.includes('T') ? iso : `${iso}Z`);
    assert.ok(!Number.isNaN(moment.getTime()), `cannot read the date '${text}'`);
    return moment;
  }

  get now(): Date | undefined {
    return this.moment;
  }

  /** Start freezing time in a context (called for every context the scenario opens). */
  async attach(context: BrowserContext): Promise<void> {
    this.contexts.add(context);
    if (this.moment) {
      await this.freeze(context, this.moment);
    }
  }

  async set(text: string): Promise<Date> {
    this.moment = Clock.parse(text);
    await Promise.all([...this.contexts].map((context) => this.freeze(context, this.moment as Date)));
    return this.moment;
  }

  async advance(text: string): Promise<Date> {
    assert.ok(this.moment, 'set the current time first (Given the current time is ...)');
    const ms = durationMs(text);
    this.moment = new Date(this.moment.getTime() + ms);
    await Promise.all([...this.contexts].map((context) => context.clock.fastForward(ms)));
    return this.moment;
  }

  private async freeze(context: BrowserContext, moment: Date): Promise<void> {
    await context.clock.install({ time: moment });
    await context.clock.pauseAt(new Date(moment.getTime() + 1));
  }
}
