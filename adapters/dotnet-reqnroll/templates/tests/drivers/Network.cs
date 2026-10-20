using System.Net;
using System.Net.Sockets;

namespace Greenlight.Tests.Drivers;

/// <summary>
/// Refuses every connection that is not to this machine, so a test that reaches for the real internet fails instead of
/// passing by luck. .NET has no global switch: give the application's HttpClient this connect callback
/// (new SocketsHttpHandler { ConnectCallback = BlockedNetwork.ConnectAsync }), or stub the dependency, which is the point.
/// </summary>
public static class BlockedNetwork
{
    public static async ValueTask<Stream> ConnectAsync(SocketsHttpConnectionContext context, CancellationToken cancellation)
    {
        var host = context.DnsEndPoint.Host;
        var local = host.Equals("localhost", StringComparison.OrdinalIgnoreCase) || (IPAddress.TryParse(host, out var address) && IPAddress.IsLoopback(address));
        if (!local)
        {
            throw new OutboundNetworkBlocked($"{host}:{context.DnsEndPoint.Port}");
        }
        var socket = new Socket(SocketType.Stream, ProtocolType.Tcp) { NoDelay = true };
        try
        {
            await socket.ConnectAsync(context.DnsEndPoint, cancellation).ConfigureAwait(false);
            return new NetworkStream(socket, ownsSocket: true);
        }
        catch
        {
            socket.Dispose();
            throw;
        }
    }
}
