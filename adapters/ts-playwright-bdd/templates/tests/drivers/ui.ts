// What a user does and sees. Selectors live in operations.ts; the steps and the features only use logical names.
// Every check waits for the condition (Playwright retries until its timeout): there are no fixed sleeps.
import { strict as assert } from 'node:assert';
import { expect, type Locator, type Page } from '@playwright/test';
import { type Data, type Row, assertSubset, parseValue, payload, rows } from './compare';
import { NotMapped } from './errors';
import { PAGES, TARGETS } from './operations';
import type { StorageItem, World } from './world';

const ABSOLUTE = /^[a-z][a-z0-9+.-]*:/i;

export type Action = 'clicks' | 'fills' | 'selects' | 'uploads' | 'types' | 'toggles' | 'swipes' | 'scrolls';

export function locate(page: Page, name: string): Locator {
  const target = TARGETS[name];
  if (!target) {
    throw new NotMapped('target', name, Object.keys(TARGETS));
  }
  if ('role' in target) {
    return page.getByRole(target.role, target.name === undefined ? {} : { name: target.name });
  }
  if ('label' in target) {
    return page.getByLabel(target.label);
  }
  if ('text' in target) {
    return page.getByText(target.text);
  }
  return page.getByTestId(target.testId);
}

function addressOf(world: World, name: string): string {
  const path = PAGES[name];
  if (path === undefined) {
    throw new NotMapped('page', name, Object.keys(PAGES));
  }
  if (ABSOLUTE.test(path)) {
    return path;
  }
  const base = new URL(world.system.baseUrl());
  world.stubs.allowHost(base.host);
  return new URL(path, base).href;
}

export async function open(world: World, actor: string, name: string): Promise<void> {
  const page = await world.page(actor);
  const url = addressOf(world, name);
  const response = await page.goto(url);
  if (response && response.status() >= 400) {
    throw new Error(`status ${response.status()} for ${url}`);
  }
}

/** The value a step carries for an action: a `value` cell, a doc string, or the only cell. */
function valueOf(data: Data, column: string): string {
  const given = payload(data);
  const found = given && typeof given === 'object' && !Array.isArray(given) ? ((given as Row)[column] ?? Object.values(given)[0]) : given;
  assert.ok(found !== undefined && found !== null, `give the ${column} in a table (| ${column} |) or a doc string`);
  return String(found);
}

/** Direction names as the unit vector the finger (a swipe) or the view (a scroll) moves in; y grows downwards. */
const DIRECTIONS: Record<string, readonly [number, number]> = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
const GESTURE_SHARE = 0.6;            // how much of the component a swipe or a scroll covers

function directionOf(data: Data): readonly [number, number] {
  const name = valueOf(data, 'direction').trim().toLowerCase();
  const vector = DIRECTIONS[name];
  assert.ok(vector, `give a direction in a table (| direction |): up, down, left or right, not '${name}'`);
  return vector;
}

/** The view moves in the direction: scrolling down shows what is below. */
async function scrollBy(locator: Locator, [x, y]: readonly [number, number]): Promise<void> {
  await locator.evaluate((element, [dx, dy, share]) => {
    element.scrollBy({ left: (dx ?? 0) * element.clientWidth * (share ?? 1), top: (dy ?? 0) * element.clientHeight * (share ?? 1) });
  }, [x, y, GESTURE_SHARE]);
}

/** The finger moves in the direction: swiping left drags from the right of the component towards its left. */
async function swipe(page: Page, locator: Locator, [x, y]: readonly [number, number]): Promise<void> {
  const box = await locator.boundingBox();
  assert.ok(box, 'the component to swipe is not on the screen');
  const reach = { x: box.width * GESTURE_SHARE / 2, y: box.height * GESTURE_SHARE / 2 };
  const middle = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  await page.mouse.move(middle.x - x * reach.x, middle.y - y * reach.y);
  await page.mouse.down();
  await page.mouse.move(middle.x + x * reach.x, middle.y + y * reach.y, { steps: 8 });
  await page.mouse.up();
}

export async function back(world: World, actor: string): Promise<void> {
  await (await world.page(actor)).goBack();
}

export async function act(world: World, actor: string, action: Action, target: string, data: Data): Promise<void> {
  const page = await world.page(actor);
  const locator = locate(page, target);
  switch (action) {
    case 'clicks':
      await locator.click();
      break;
    case 'fills':
      await locator.fill(valueOf(data, 'value'));
      break;
    case 'types':
      await locator.pressSequentially(valueOf(data, 'value'));
      break;
    case 'selects':
      await locator.selectOption(valueOf(data, 'value'));
      break;
    case 'uploads':
      await locator.setInputFiles(valueOf(data, 'file'));
      break;
    case 'toggles':
      await locator.setChecked(!(await locator.isChecked()));
      break;
    case 'swipes':
      await swipe(page, locator, directionOf(data));
      break;
    case 'scrolls':
      await scrollBy(locator, directionOf(data));
      break;
  }
}

/** The visible state of a component: `text`, `value`, `enabled`, `checked`, `visible` columns, or an `item` column with
 *  one row per entry of a list. */
export async function assertShows(world: World, actor: string, target: string, data: Data): Promise<void> {
  const locator = locate(await world.page(actor), target);
  if (typeof data === 'string') {
    await expect(locator).toHaveText(data.trim());
    return;
  }
  const table = rows(data);
  if (table.length > 0 && table.every((row) => 'item' in row)) {
    await expect(locator).toHaveText(table.map((row) => String(row.item)));
    return;
  }
  const [expected = {}] = table;
  if (expected.visible !== false) {
    await expect(locator).toBeVisible();
  }
  await Promise.all(Object.entries(expected).map(([column, value]) => expectColumn(locator, column, value)));
}

async function expectColumn(locator: Locator, column: string, value: unknown): Promise<void> {
  switch (column) {
    case 'text':
      await expect(locator).toHaveText(String(value));
      break;
    case 'value':
      await expect(locator).toHaveValue(String(value));
      break;
    case 'enabled':
      await (value === false ? expect(locator).toBeDisabled() : expect(locator).toBeEnabled());
      break;
    case 'checked':
      await expect(locator).toBeChecked({ checked: value !== false });
      break;
    case 'visible':
      await (value === false ? expect(locator).toBeHidden() : expect(locator).toBeVisible());
      break;
    default:
      throw new NotMapped('column', column, ['text', 'value', 'enabled', 'checked', 'visible', 'item']);
  }
}

export async function assertHidden(world: World, actor: string, target: string): Promise<void> {
  await expect(locate(await world.page(actor), target)).toBeHidden();
}

/** `| key | value |` rows (and an optional `storage` column: local or session) as storage items. */
export function storageItems(table: Data): StorageItem[] {
  assert.ok(typeof table !== 'string', 'the application state is a table with the columns key and value');
  return rows(table).map((row) => {
    assert.ok(typeof row.key === 'string' && 'value' in row, 'each row of the application state needs a key and a value');
    return { storage: row.storage === 'session' ? 'session' : 'local', key: row.key, value: String(row.value) };
  });
}

/** Checks the browser storage of the page that is open against the `key`/`value` rows. */
export async function assertState(world: World, table: Data): Promise<void> {
  const page = world.current();
  await Promise.all(storageItems(table).map(async (item) => {
    const stored = await page.evaluate(
      ({ storage, key }) => (storage === 'session' ? window.sessionStorage : window.localStorage).getItem(key),
      { storage: item.storage, key: item.key },
    );
    assert.notEqual(stored, null, `the application state has no ${item.storage} storage entry '${item.key}'`);
    assertSubset(parseValue(stored as string), parseValue(item.value), `the ${item.storage} storage entry '${item.key}'`);
  }));
}
