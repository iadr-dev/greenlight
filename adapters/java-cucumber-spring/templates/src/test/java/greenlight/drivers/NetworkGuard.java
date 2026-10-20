package greenlight.drivers;

import java.io.IOException;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.util.List;
import java.util.Set;

/**
 * Refuses outbound HTTP connections to anything but this machine, for code that uses the JDK's {@code HttpClient} or
 * {@code HttpURLConnection} (and so Spring's RestClient, RestTemplate and WebClient on the JDK client).
 *
 * <p>This is a guard, not a firewall: a library that opens raw sockets itself is not covered, because the JVM no
 * longer offers a process-wide hook for that. For the rest, stub the dependency and run the tests without network
 * access in CI.
 */
public final class NetworkGuard extends ProxySelector {
    private static final Set<String> LOCAL = Set.of("localhost", "127.0.0.1", "::1", "[::1]", "testserver");
    private static volatile boolean installed;

    private NetworkGuard() {
    }

    public static synchronized void install() {
        if (!installed) {
            ProxySelector.setDefault(new NetworkGuard());
            installed = true;
        }
    }

    @Override
    public List<Proxy> select(URI uri) {
        String host = uri == null ? null : uri.getHost();
        if (host != null && !LOCAL.contains(host.toLowerCase())) {
            throw new Errors.OutboundNetworkBlocked("a real connection to " + host + " was attempted. Stub the dependency instead.");
        }
        return List.of(Proxy.NO_PROXY);
    }

    @Override
    public void connectFailed(URI uri, SocketAddress address, IOException failure) {
        // nothing to do: connections that are allowed go direct
    }
}
