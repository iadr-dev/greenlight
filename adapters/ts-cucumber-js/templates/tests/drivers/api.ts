// Calling an API operation by its logical name and judging the response by logical result.
import { strict as assert } from 'node:assert';
import { NotMapped } from './errors';
import { API, type Api } from './operations';
import type { GreenlightWorld } from './world';

type Fields = Record<string, unknown>;

export interface HttpResponse {
  status: number;
  body: unknown;
}

export interface RequestOptions {
  json?: unknown;
  params?: Fields;
  headers?: Record<string, string>;
}

export interface HttpClient {
  request(method: string, path: string, options?: RequestOptions): Promise<HttpResponse>;
}

/** The body of a response: JSON when it parses, else the text. */
function parseBody(text: string): unknown {
  try {
    return text === '' ? null : JSON.parse(text);
  } catch {
    return text;
  }
}

/** An HttpClient on `fetch` for an application listening at `baseUrl`. Loopback is let through by the network guard. */
export function httpClient(baseUrl: string): HttpClient {
  return {
    async request(method, path, options) {
      const { json, params, headers } = options ?? {};
      const url = new URL(path, baseUrl);
      Object.entries(params ?? {}).forEach(([key, value]) => url.searchParams.set(key, String(value)));
      const response = await fetch(url, {
        method,
        headers: json === undefined ? headers : { ...headers, 'content-type': 'application/json' },
        body: json === undefined ? undefined : JSON.stringify(json),
      });
      return { status: response.status, body: parseBody(await response.text()) };
    },
  };
}

const isFields = (value: unknown): value is Fields => typeof value === 'object' && value !== null && !Array.isArray(value);
const isEmpty = (value: unknown): boolean => value === undefined || value === null || (typeof value === 'object' && Object.keys(value).length === 0);

/** The route's path with its `{field}` placeholders filled in, and the request data that is left over. */
function addressed(route: Api, fields: Fields, data: unknown): { path: string; sent: unknown } {
  const used = new Set<string>();
  const path = route.path.replace(/\{(\w+)\}/g, (_all, name: string) => {
    used.add(name);
    return encodeURIComponent(String(fields[name]));
  });
  const sent = isFields(data) || Object.keys(fields).length > 0
    ? Object.fromEntries(Object.entries(fields).filter(([key]) => !used.has(key)))
    : data;
  return { path, sent };
}

/** A GET carries its data in the query string, any other method in a JSON body. */
function carrying(method: string, sent: unknown): RequestOptions {
  if (isEmpty(sent)) {
    return {};
  }
  return method === 'GET' ? { params: sent as Fields } : { json: sent };
}

export async function call(world: GreenlightWorld, actor: string, operation: string, data: unknown): Promise<void> {
  const route = API[operation];
  if (route === undefined) {
    throw new NotMapped('API operation', operation, Object.keys(API));
  }
  const fields = world.system.complete(operation, isFields(data) ? data : {});      // the project may add what the scenario left out
  const { path, sent } = addressed(route, fields, data);
  const method = route.method.toUpperCase();
  const headers = world.headers.get(actor);
  const response = await world.system.http().request(method, path, { ...carrying(method, sent), ...(headers && { headers }) });
  world.outcome = { kind: 'api', status: response.status, body: response.body, operation, stdout: '', stderr: '' };
}

export function assertSucceeds(world: GreenlightWorld): void {
  const { status = 0, body } = world.last('api');
  assert.ok(status >= 200 && status < 300, `the request should succeed but got status ${status}: ${JSON.stringify(body)}`);
}

export function assertRejected(world: GreenlightWorld, error: string): void {
  const outcome = world.last('api');
  assert.ok((outcome.status ?? 0) >= 400, `the request should be rejected but got status ${outcome.status}`);
  assert.ok(world.matchesError(outcome, error),
    `the request was rejected, but not with '${error}': status ${outcome.status}, ${JSON.stringify(outcome.body)}`);
}
