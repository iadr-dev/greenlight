// The scenario's clock. Application code reads `world.clock.now()` (or is handed it through System.setTime); the process
// clock is not frozen, so give the application a clock seam and note it in system.md.
import { strict as assert } from 'node:assert';
import { durationMs } from './compare';

const HAS_ZONE = /(Z|[+-]\d\d:?\d\d)$/;

/** An ISO date or date-time ("2026-03-01", "2026-03-01 09:30", "2026-03-01T09:30:00Z"); no zone means UTC. */
export function parseMoment(text: string): Date {
  const iso = text.trim().replace(' ', 'T');
  const moment = new Date(iso.includes('T') && !HAS_ZONE.test(iso) ? `${iso}Z` : iso);
  assert.ok(!Number.isNaN(moment.getTime()), `cannot read the date '${text}'`);
  return moment;
}

export class Clock {
  private moment: Date | undefined;

  /** The scenario's time: the one it set, or the real time when it set none. */
  now(): Date {
    return this.moment ?? new Date();
  }

  set(text: string): Date {
    this.moment = parseMoment(text);
    return this.moment;
  }

  advance(text: string): Date {
    assert.ok(this.moment, 'set the current time first (Given the current time is ...)');
    this.moment = new Date(this.moment.getTime() + durationMs(text));
    return this.moment;
  }
}
