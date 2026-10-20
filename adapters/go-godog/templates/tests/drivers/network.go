package drivers

import (
	"context"
	"net"
	"net/http"
)

// BlockNetwork makes the default HTTP transport refuse every connection that is not to this machine, so a test that
// reaches for the real internet fails instead of passing by luck. Clients that build their own transport or dialer
// are not covered: give them DialBlocked (or stub the dependency, which is the point). Called once from TestFeatures.
func BlockNetwork() {
	if transport, ok := http.DefaultTransport.(*http.Transport); ok {
		blocked := transport.Clone()
		blocked.DialContext = DialBlocked
		http.DefaultTransport = blocked
	}
}

// DialBlocked is a dialer that allows loopback addresses only.
func DialBlocked(ctx context.Context, network, address string) (net.Conn, error) {
	host, _, err := net.SplitHostPort(address)
	if err != nil {
		host = address
	}
	if host == "localhost" {
		return (&net.Dialer{}).DialContext(ctx, network, address)
	}
	if ip := net.ParseIP(host); ip != nil && ip.IsLoopback() {
		return (&net.Dialer{}).DialContext(ctx, network, address)
	}
	return nil, OutboundNetworkBlocked{Address: address}
}
