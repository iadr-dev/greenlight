// The scenario's clock. Application code reads `world.clock.now()` (or is handed it through System.setTime); the
// process clock is not frozen, so give the application a clock seam and note it in system.md.
import { strict as assert } from 'node:assert';
import { durationMs } from './compare';

export class Clock {
  private moment: Date | undefined;

  /** Parse an ISO date or date-time ("2026-03-01", "2026-03-01 09:30", "2026-03-01T09:30:00Z"); no zone means UTC. */
  static parse(text: string): Date {
    const iso = text.trim().replace(' ', 'T');
    const moment = new Date(/(Z|[+-]\d\d:?\d\d)$/.test(iso) || !iso.includes('T') ? iso : `${iso}Z`);
    assert.ok(!Number.isNaN(moment.getTime()), `cannot read the date '${text}'`);
    return moment;
  }

  /** The scenario's time: the one it set, or the real time when it set none. */
  now(): Date {
    return this.moment ?? new Date();
  }

  set(text: string): Date {
    this.moment = Clock.parse(text);
    return this.moment;
  }

  advance(text: string): Date {
    assert.ok(this.moment, 'set the current time first (Given the current time is ...)');
    this.moment = new Date(this.moment.getTime() + durationMs(text));
    return this.moment;
  }
}
