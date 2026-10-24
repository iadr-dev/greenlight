// Calling an API operation by its logical name and judging the response by logical result.
import { strict as assert } from 'node:assert';
import { NotMapped } from './errors';
import { API } from './operations';
import type { GreenlightWorld } from './world';

export interface HttpResponse {
  status: number;
  body: unknown;
}

export interface HttpClient {
  request(method: string, path: string, options?: { json?: unknown; params?: Record<string, unknown>; headers?: Record<string, string> }): Promise<HttpResponse>;
}

/** An HttpClient on `fetch` for an application listening at `baseUrl`. Loopback is let through by the network guard. */
export function httpClient(baseUrl: string): HttpClient {
  return {
    async request(method, path, options = {}) {
      const url = new URL(path, baseUrl);
      for (const [key, value] of Object.entries(options.params ?? {})) {
        url.searchParams.set(key, String(value));
      }
      const headers: Record<string, string> = { ...(options.headers ?? {}) };
      if (options.json !== undefined) {
        headers['content-type'] = 'application/json';
      }
      const response = await fetch(url, { method, headers, body: options.json === undefined ? undefined : JSON.stringify(options.json) });
      const text = await response.text();
      let body: unknown = text;
      try {
        body = text === '' ? null : JSON.parse(text);
      } catch {
        // not JSON: keep the text
      }
      return { status: response.status, body };
    },
  };
}

export async function call(world: GreenlightWorld, actor: string, operation: string, data: unknown): Promise<void> {
  const route = API[operation];
  if (route === undefined) {
    throw new NotMapped('API operation', operation, Object.keys(API));
  }
  const given = data && typeof data === 'object' && !Array.isArray(data) ? (data as Record<string, unknown>) : {};
  const fields = world.system.complete(operation, given);          // the project may add what the scenario left out
  const path = route.path.replace(/\{(\w+)\}/g, (_all, name: string) => encodeURIComponent(String(fields[name])));
  const used = new Set([...route.path.matchAll(/\{(\w+)\}/g)].map((m) => m[1]));
  const sent = Object.keys(fields).length > 0 || (data && typeof data === 'object' && !Array.isArray(data))
    ? Object.fromEntries(Object.entries(fields).filter(([key]) => !used.has(key)))
    : data;
  const isGet = route.method.toUpperCase() === 'GET';
  const empty = sent === undefined || sent === null || (typeof sent === 'object' && Object.keys(sent).length === 0);
  const response = await world.system.http().request(route.method.toUpperCase(), path, {
    headers: world.headers.get(actor) ?? {},
    ...(empty ? {} : isGet ? { params: sent as Record<string, unknown> } : { json: sent }),
  });
  world.outcome = { kind: 'api', status: response.status, body: response.body, operation, stdout: '', stderr: '' };
}

export function assertSucceeds(world: GreenlightWorld): void {
  const outcome = world.last('api');
  assert.ok((outcome.status ?? 0) >= 200 && (outcome.status ?? 0) < 300,
    `the request should succeed but got status ${outcome.status}: ${JSON.stringify(outcome.body)}`);
}

export function assertRejected(world: GreenlightWorld, error: string): void {
  const outcome = world.last('api');
  assert.ok((outcome.status ?? 0) >= 400, `the request should be rejected but got status ${outcome.status}`);
  assert.ok(world.matchesError(outcome, error),
    `the request was rejected, but not with '${error}': status ${outcome.status}, ${JSON.stringify(outcome.body)}`);
}
