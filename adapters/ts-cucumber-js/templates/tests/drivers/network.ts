// Block real outbound network connections during a scenario (loopback stays allowed).
//
// Node's HTTP clients (fetch, http, https) all open their connections through `net.Socket.prototype.connect`, so one guard
// there covers them. A client that opens sockets in native code (some database drivers) is not covered: run the tests
// without network access in CI for those.
import net from 'node:net';
import { OutboundNetworkBlocked } from './errors';

const LOOPBACK = new Set(['127.0.0.1', '::1', 'localhost', '[::1]']);

type Connect = (this: net.Socket, ...args: unknown[]) => net.Socket;

let original: Connect | undefined;

function hostOf(args: unknown[]): string | undefined {
  const first = args[0];
  if (first && typeof first === 'object' && !Array.isArray(first)) {
    const options = first as { host?: string; path?: string };
    return options.path ? undefined : (options.host ?? 'localhost');      // a path is a local socket
  }
  return typeof first === 'number' ? (typeof args[1] === 'string' ? args[1] : 'localhost') : undefined;
}

export function blockNetwork(allowed: ReadonlySet<string> = new Set()): void {
  if (original) {
    return;
  }
  original = net.Socket.prototype.connect as unknown as Connect;
  net.Socket.prototype.connect = function guarded(this: net.Socket, ...args: unknown[]): net.Socket {
    const host = hostOf(args);
    if (host !== undefined && !LOOPBACK.has(host) && !allowed.has(host)) {
      throw new OutboundNetworkBlocked(`a real connection to ${host} was attempted; stub the dependency (Given ... responds to ...)`);
    }
    return (original as Connect).apply(this, args);
  } as typeof net.Socket.prototype.connect;
}

export function unblockNetwork(): void {
  if (original) {
    net.Socket.prototype.connect = original as unknown as typeof net.Socket.prototype.connect;
    original = undefined;
  }
}
