// Turning Gherkin tables and doc strings into data, and comparing data the way the instructions say.
import { strict as assert } from 'node:assert';
import type { DataTable } from 'playwright-bdd';

export type Data = string | DataTable | undefined;
export type Row = Record<string, unknown>;

/** A cell or doc string as data: JSON when it parses (numbers, true, null, lists, objects), else the text. */
export function parseValue(text: string): unknown {
  const trimmed = text.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    return trimmed;
  }
}

/** A table with a header row as a list of objects. */
export function rows(table: DataTable | undefined): Row[] {
  if (!table) {
    return [];
  }
  const [header = [], ...body] = table.raw();
  return body.map((cells) => Object.fromEntries(header.map((name, at) => [name, parseValue(cells[at] ?? '')])));
}

/** The data a step carries: a doc string as JSON or text, or a table (one row becomes an object). */
export function payload(data: Data): unknown {
  if (typeof data === 'string') {
    return parseValue(data);
  }
  const found = rows(data);
  return found.length === 1 ? found[0] : found;
}

/** A stable order for comparing record sets, where the order does not matter. */
export function sortKey(row: unknown): string {
  return JSON.stringify(row, (_key, value: unknown) =>
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)))
      : value);
}

export function assertEqual(actual: unknown, expected: unknown, what: string): void {
  assert.deepEqual(actual, expected, `${what}: expected ${JSON.stringify(expected)} but got ${JSON.stringify(actual)}`);
}

/** Every field of `expected` is in `actual` (recursively); lists must contain each expected item. */
export function assertSubset(actual: unknown, expected: unknown, what: string): void {
  const problem = subsetProblem(actual, expected, '');
  assert.equal(problem, null, `${what}: ${problem} (actual: ${JSON.stringify(actual)})`);
}

function subsetProblem(actual: unknown, expected: unknown, path: string): string | null {
  const here = path || 'value';
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) {
      return `${here} should be a list`;
    }
    const missing = expected.find((item) => !actual.some((candidate) => subsetProblem(candidate, item, path) === null));
    return missing === undefined ? null : `${here} has no item matching ${JSON.stringify(missing)}`;
  }
  if (expected && typeof expected === 'object') {
    if (!actual || typeof actual !== 'object' || Array.isArray(actual)) {
      return `${here} should be an object`;
    }
    for (const [key, value] of Object.entries(expected)) {
      const where = path ? `${path}.${key}` : key;
      if (!(key in actual)) {
        return `${where} is missing`;
      }
      const problem = subsetProblem((actual as Row)[key], value, where);
      if (problem) {
        return problem;
      }
    }
    return null;
  }
  return Object.is(actual, expected) ? null : `${here} is ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`;
}

const UNITS: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86400, w: 604800 };
const DURATION = /(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\b/gi;

/** '2 days', '30 minutes', '1h 30m' as milliseconds. */
export function durationMs(text: string): number {
  const found = [...text.matchAll(DURATION)];
  const rest = text.replace(DURATION, '').replace(/[\s,]|and/g, '');
  assert.ok(found.length > 0 && rest === '', `cannot read the duration '${text}'`);
  return found.reduce((total, [, amount, unit]) => total + Number(amount) * (UNITS[(unit ?? 's').charAt(0).toLowerCase()] ?? 1) * 1000, 0);
}
