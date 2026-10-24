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
  if (Array.isArray(expected)) {
    return listMismatch(actual, expected, at);
  }
  if (isObject(expected)) {
    return objectMismatch(actual, expected, at);
  }
  return Object.is(actual, expected) ? null : `${at || 'value'} is ${show(actual)}, expected ${show(expected)}`;
}

function listMismatch(actual: unknown, expected: unknown[], at: string): string | null {
  if (!Array.isArray(actual)) {
    return `${at || 'value'} should be a list`;
  }
  const missing = expected.find((item) => !actual.some((candidate) => mismatch(candidate, item, at) === null));
  return missing === undefined ? null : `${at || 'value'} has no item matching ${show(missing)}`;
}

function objectMismatch(actual: unknown, expected: Row, at: string): string | null {
  if (!isObject(actual)) {
    return `${at || 'value'} should be an object`;
  }
  const where = (key: string): string => (at ? `${at}.${key}` : key);
  const problems = Object.entries(expected).map(([key, value]) => (key in actual ? mismatch(actual[key], value, where(key)) : `${where(key)} is missing`));
  return problems.find((problem) => problem !== null) ?? null;
}

const SECONDS_PER_UNIT: Record<string, number> = {
  s: 1, sec: 1, secs: 1, second: 1, seconds: 1,
  m: 60, min: 60, mins: 60, minute: 60, minutes: 60,
  h: 3600, hr: 3600, hrs: 3600, hour: 3600, hours: 3600,
  d: 86_400, day: 86_400, days: 86_400,
  w: 604_800, week: 604_800, weeks: 604_800,
};
const AMOUNT = /(\d+(?:\.\d+)?)\s?([a-z]+)/g;      // one optional space keeps the match linear

/** '2 days', '30 minutes', '1h 30m' as milliseconds. An amount is a number and a unit; "and" and commas are ignored. */
export function durationMs(text: string): number {
  const lower = text.toLowerCase();
  const amounts = [...lower.matchAll(AMOUNT)];
  const leftover = lower.replace(AMOUNT, '').replace(/\band\b|[\s,]/g, '');
  const seconds = amounts.map(([, amount, unit]) => Number(amount) * (SECONDS_PER_UNIT[unit as string] ?? Number.NaN));
  assert.ok(amounts.length > 0 && leftover === '' && seconds.every(Number.isFinite), `cannot read the duration '${text}'`);
  return seconds.reduce((sum, value) => sum + value, 0) * 1000;
}
