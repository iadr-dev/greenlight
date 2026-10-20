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
  if (Array.isArray(expected)) {
    return listProblem(actual, expected, path);
  }
  if (expected && typeof expected === 'object') {
    return objectProblem(actual, expected as Row, path);
  }
  return Object.is(actual, expected) ? null : `${path || 'value'} is ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`;
}

function listProblem(actual: unknown, expected: unknown[], path: string): string | null {
  if (!Array.isArray(actual)) {
    return `${path || 'value'} should be a list`;
  }
  const missing = expected.find((item) => !actual.some((candidate) => subsetProblem(candidate, item, path) === null));
  return missing === undefined ? null : `${path || 'value'} has no item matching ${JSON.stringify(missing)}`;
}

function objectProblem(actual: unknown, expected: Row, path: string): string | null {
  if (!actual || typeof actual !== 'object' || Array.isArray(actual)) {
    return `${path || 'value'} should be an object`;
  }
  for (const [key, value] of Object.entries(expected)) {
    const where = path ? `${path}.${key}` : key;
    const problem = key in actual ? subsetProblem((actual as Row)[key], value, where) : `${where} is missing`;
    if (problem) {
      return problem;
    }
  }
  return null;
}

const SECONDS: Record<string, number> = {
  s: 1, sec: 1, secs: 1, second: 1, seconds: 1,
  m: 60, min: 60, mins: 60, minute: 60, minutes: 60,
  h: 3600, hr: 3600, hrs: 3600, hour: 3600, hours: 3600,
  d: 86400, day: 86400, days: 86400,
  w: 604800, week: 604800, weeks: 604800,
};
const AMOUNT_AND_UNIT = /(\d+(?:\.\d+)?)\s*([a-z]+)/gi;

/** '2 days', '30 minutes', '1h 30m' as milliseconds. */
export function durationMs(text: string): number {
  const found = [...text.matchAll(AMOUNT_AND_UNIT)];
  const rest = text.replaceAll(AMOUNT_AND_UNIT, '').replaceAll(/[\s,]|and/g, '');
  const unknown = found.find(([, , unit]) => SECONDS[(unit ?? '').toLowerCase()] === undefined);
  assert.ok(found.length > 0 && rest === '' && unknown === undefined, `cannot read the duration '${text}'`);
  return found.reduce((total, [, amount, unit]) => total + Number(amount) * (SECONDS[(unit ?? '').toLowerCase()] ?? 0) * 1000, 0);
}
