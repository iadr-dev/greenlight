// Turning Gherkin tables and doc strings into data, and comparing data the way the instructions say.
import { strict as assert } from 'node:assert';
import type { DataTable } from '@cucumber/cucumber';

/** What a step receives after its captures: a doc string, a table, or nothing. */
export type Data = string | DataTable | undefined;
export type Row = Record<string, unknown>;

const isObject = (value: unknown): value is Row => typeof value === 'object' && value !== null && !Array.isArray(value);
const show = (value: unknown): string => JSON.stringify(value);

/** A cell or doc string as data: JSON when it parses (numbers, true, null, lists, objects), else the text. */
export function parseValue(text: string): unknown {
  try {
    return JSON.parse(text.trim());
  } catch {
    return text.trim();
  }
}

/** A table with a header row as a list of objects. */
export function rows(table: DataTable | undefined): Row[] {
  const [header, ...body] = table?.raw() ?? [];
  return body.map((cells) => Object.fromEntries((header ?? []).map((name, at) => [name, parseValue(cells[at] ?? '')])));
}

/** The data a step carries: a doc string as JSON or text, or a table (one row becomes an object). */
export function payload(data: Data): unknown {
  if (typeof data !== 'string') {
    const found = rows(data);
    return found.length === 1 ? found[0] : found;
  }
  return parseValue(data);
}

/** The text a step carries: a doc string as it is, or a table as comma-separated lines. */
export function textOf(data: Data): string {
  return typeof data === 'string' ? data : (data?.raw() ?? []).map((row) => row.join(',')).join('\n');
}

/** A stable order for comparing record sets, where the order does not matter. */
export function sortKey(row: unknown): string {
  return JSON.stringify(row, (_key, value: unknown) =>
    isObject(value) ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b))) : value);
}

/** Line endings, trailing spaces and blank lines do not matter. */
export function normaliseText(text: string): string {
  return text.split(/\r?\n/).map((line) => line.trimEnd()).filter((line) => line.trim() !== '').join('\n');
}

export function assertEqual(actual: unknown, expected: unknown, what: string): void {
  assert.deepEqual(actual, expected, `${what}: expected ${show(expected)} but got ${show(actual)}`);
}

export function assertTextContains(actual: string, expected: string, what: string): void {
  const [wanted, got] = [normaliseText(expected), normaliseText(actual)];
  assert.ok(got.includes(wanted), `${what} does not contain ${show(wanted)}; it is ${show(got)}`);
}

/** Every field of `expected` is in `actual` (recursively); a list must contain an item matching each expected item. */
export function assertSubset(actual: unknown, expected: unknown, what: string): void {
  const problem = mismatch(actual, expected, '');
  assert.equal(problem, null, `${what}: ${problem} (actual: ${show(actual)})`);
}

/** Why `actual` does not contain `expected`, or null when it does. `at` names the place, such as `order.lines`. */
function mismatch(actual: unknown, expected: unknown, at: string): string | null {
  const place = at || 'value';
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) {
      return `${place} should be a list`;
    }
    const missing = expected.find((item) => !actual.some((candidate) => mismatch(candidate, item, at) === null));
    return missing === undefined ? null : `${place} has no item matching ${show(missing)}`;
  }
  if (isObject(expected)) {
    if (!isObject(actual)) {
      return `${place} should be an object`;
    }
    for (const [key, value] of Object.entries(expected)) {
      const where = at ? `${at}.${key}` : key;
      const problem = key in actual ? mismatch(actual[key], value, where) : `${where} is missing`;
      if (problem !== null) {
        return problem;
      }
    }
    return null;
  }
  return Object.is(actual, expected) ? null : `${place} is ${show(actual)}, expected ${show(expected)}`;
}

const UNIT_SECONDS: Record<string, number> = { s: 1, m: 60, h: 3600, d: 86_400, w: 604_800 };
const AMOUNT = /(\d+(?:\.\d+)?)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|[smhdw])\b/g;

/** '2 days', '30 minutes', '1h 30m' as milliseconds: each amount is a number and a unit (the first letter says which). */
export function durationMs(text: string): number {
  const lower = text.toLowerCase();
  const amounts = [...lower.matchAll(AMOUNT)];
  const leftover = lower.replace(AMOUNT, '').replace(/\band\b|[\s,]/g, '');
  assert.ok(amounts.length > 0 && leftover === '', `cannot read the duration '${text}'`);
  const seconds = amounts.map(([, amount, unit]) => Number(amount) * (UNIT_SECONDS[(unit as string).charAt(0)] as number));
  return seconds.reduce((sum, value) => sum + value, 0) * 1000;
}
