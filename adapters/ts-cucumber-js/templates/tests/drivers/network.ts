// Block real outbound network connections during a scenario (loopback stays allowed).
//
// Node's HTTP clients (fetch, http, https) all open their connections through `net.Socket.prototype.connect`, so one guard
// there covers them. The guard fails closed: a call whose target it cannot read is refused, and a name that is allowed
// (`localhost`) must also resolve to a loopback address. A client that opens sockets in native code (some database drivers)
// is not covered: run the tests without network access in CI for those.
import net from 'node:net';
import { OutboundNetworkBlocked } from './errors';

const LOOPBACK = new Set(['127.0.0.1', '::1', 'localhost', '[::1]']);
const LOOPBACK_ADDRESS = /^(127\.\d+\.\d+\.\d+|::1|::ffff:127\.\d+\.\d+\.\d+)$/;

type Connect = (this: net.Socket, ...args: unknown[]) => net.Socket;
type Target = { local: true } | { local: false; host: string };

let original: Connect | undefined;

function fromOptions(options: { host?: unknown; path?: unknown; port?: unknown }): Target | undefined {
  if (typeof options.path === 'string' && options.path !== '') {
    return { local: true };                                                            // a path is a local socket
  }
  if (options.host === undefined || options.host === '') {
    return options.port === undefined ? undefined : { local: false, host: 'localhost' };
  }
  return typeof options.host === 'string' ? { local: false, host: options.host } : undefined;
}

/** Where a call to `connect` goes. Node calls it as `connect(options)`, `connect(port, host)`, `connect(path)` and, when it
 *  re-enters itself, with the already-normalised `[options, callback]`; anything else is unreadable. */
function targetOf(args: unknown[]): Target | undefined {
  const first = Array.isArray(args[0]) ? (args[0] as unknown[])[0] : args[0];        // unwrap the normalised form
  if (typeof first === 'object' && first !== null) {
    return fromOptions(first);
  }
  if (typeof first === 'number' || (typeof first === 'string' && /^\d+$/.test(first))) {
    return { local: false, host: typeof args[1] === 'string' ? args[1] : 'localhost' };
  }
  return typeof first === 'string' && first !== '' ? { local: true } : undefined;      // a string that is not a port is a socket path
}

export function blockNetwork(allowed: ReadonlySet<string> = new Set()): void {
  if (original) {
    return;
  }
  original = net.Socket.prototype.connect as unknown as Connect;
  net.Socket.prototype.connect = function guarded(this: net.Socket, ...args: unknown[]): net.Socket {
    const target = targetOf(args);
    if (target === undefined) {
      throw new OutboundNetworkBlocked('a connection was attempted whose target the guard could not read; stub the dependency (Given ... responds to ...)');
    }
    if (!target.local) {
      const { host } = target;
      if (!LOOPBACK.has(host) && !allowed.has(host)) {
        throw new OutboundNetworkBlocked(`a real connection to ${host} was attempted; stub the dependency (Given ... responds to ...)`);
      }
      if (LOOPBACK.has(host) && !net.isIP(host.replace(/^\[|\]$/g, ''))) {
        // a name such as `localhost` must resolve to this machine
        this.once('lookup', (error: Error | null, address: string) => {
          if (!error && !LOOPBACK_ADDRESS.test(address)) {
            this.destroy(new OutboundNetworkBlocked(`${host} resolved to ${address}, which is not this machine; stub the dependency`));
          }
        });
      }
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
