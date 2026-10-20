// External HTTP dependencies are replaced by recorded responses, and nothing else may leave the machine.
//
// A request from the page is let through only if it goes to the application itself (the base URL, localhost) or to a
// local scheme (file, data, blob, about). A request that belongs to a dependency named in operations.ts is answered
// with the response the scenario gave, or refused if it gave none. Every other request is refused. Refused requests
// fail the scenario when it ends.
import type { BrowserContext, Route } from '@playwright/test';
import { DEPENDENCIES, type Endpoint } from './operations';
import { assertSubset } from './compare';
import { NotMapped, OutboundNetworkBlocked, UnstubbedCall } from './errors';

const LOCAL_SCHEMES = new Set(['file:', 'data:', 'blob:', 'about:']);
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);
// A stubbed dependency answers like a service that lets the page read its responses.
const CORS = { 'access-control-allow-origin': '*', 'access-control-allow-methods': '*', 'access-control-allow-headers': '*' };

interface Call {
  dependency: string;
  operation: string;
  body: unknown;
}

export class Stubs {
  private readonly responses = new Map<string, unknown>();
  private readonly calls: Call[] = [];
  private readonly unstubbed: string[] = [];
  private readonly blocked: string[] = [];
  private applicationHost: string | undefined;

  /** The application's own host is never a dependency. */
  allowHost(host: string): void {
    this.applicationHost = host;
  }

  respond(dependency: string, operation: string, body: unknown): void {
    this.endpoint(dependency, operation);
    this.responses.set(`${dependency}.${operation}`, body);
  }

  async attach(context: BrowserContext): Promise<void> {
    await context.route('**/*', (route) => this.handle(route));
  }

  assertReceived(dependency: string, operation: string, expected: unknown): void {
    this.endpoint(dependency, operation);
    const bodies = this.calls.filter((c) => c.dependency === dependency && c.operation === operation).map((c) => c.body);
    assertSubset(bodies, [expected], `the ${operation} requests received by ${dependency}`);
  }

  /** Fails the scenario if anything was refused. */
  assertClean(): void {
    if (this.unstubbed.length > 0) {
      throw new UnstubbedCall(`the page called ${this.unstubbed.join(', ')} but the scenario gave no response for it`);
    }
    if (this.blocked.length > 0) {
      throw new OutboundNetworkBlocked(`the page tried to reach ${this.blocked.join(', ')}; stub the dependency instead`);
    }
  }

  private endpoint(dependency: string, operation: string): Endpoint {
    const operations = DEPENDENCIES[dependency];
    if (!operations) {
      throw new NotMapped('dependency', dependency, Object.keys(DEPENDENCIES));
    }
    const found = operations[operation];
    if (!found) {
      throw new NotMapped(`operation of ${dependency}`, operation, Object.keys(operations));
    }
    return found;
  }

  private isLocal(url: URL): boolean {
    return LOCAL_SCHEMES.has(url.protocol) || LOCAL_HOSTS.has(url.hostname) || url.host === this.applicationHost;
  }

  private async handle(route: Route): Promise<void> {
    const request = route.request();
    const url = new URL(request.url());
    if (this.isLocal(url)) {
      await route.continue();
      return;
    }
    const found = this.match(request.url());
    if (found && request.method() === 'OPTIONS') {
      await route.fulfill({ status: 204, headers: CORS });
    } else if (found && found.method === request.method()) {
      await this.answer(route, found.dependency, found.operation, request.postData());
    } else {
      this.blocked.push(`${request.method()} ${request.url()}`);
      await route.abort('blockedbyclient');
    }
  }

  /** The dependency operation whose URL this is, if any. */
  private match(url: string): { dependency: string; operation: string; method: string } | undefined {
    for (const [dependency, operations] of Object.entries(DEPENDENCIES)) {
      for (const [operation, endpoint] of Object.entries(operations)) {
        if (endpoint.url.test(url)) {
          return { dependency, operation, method: endpoint.method };
        }
      }
    }
    return undefined;
  }

  private async answer(route: Route, dependency: string, operation: string, body: string | null): Promise<void> {
    const key = `${dependency}.${operation}`;
    if (!this.responses.has(key)) {
      this.unstubbed.push(`${dependency}.${operation}`);
      await route.abort('blockedbyclient');
      return;
    }
    this.calls.push({ dependency, operation, body: body === null ? null : safeJson(body) });
    await route.fulfill({ status: 200, contentType: 'application/json', headers: CORS, body: JSON.stringify(this.responses.get(key)) });
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
