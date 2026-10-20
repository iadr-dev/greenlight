using System.Text.Json.Nodes;

namespace Greenlight.Tests.Drivers;

/// <summary>
/// Stubbed external dependencies. Route the application's outbound calls through Call(dependency, operation, request)
/// (a gateway interface, or an HttpMessageHandler built on it). A call the scenario did not stub fails the scenario.
/// </summary>
public sealed class Stubs
{
    private readonly Dictionary<(string, string), JsonNode?> _responses = [];
    private readonly List<(string Dependency, string Operation, JsonNode? Request)> _calls = [];

    public void Respond(string dependency, string operation, JsonNode? response) =>
        _responses[(dependency, operation)] = response;

    public JsonNode? Call(string dependency, string operation, JsonNode? request = null)
    {
        _calls.Add((dependency, operation, request));
        return _responses.TryGetValue((dependency, operation), out var response)
            ? response?.DeepClone()
            : throw new UnstubbedCall(dependency, operation);
    }

    public void AssertReceived(string dependency, string operation, JsonNode? expected)
    {
        var requests = _calls.Where(call => call.Dependency == dependency && call.Operation == operation).Select(call => call.Request).ToList();
        if (requests.Count == 0)
        {
            var seen = string.Join(", ", _calls.Select(call => $"{call.Dependency}/{call.Operation}"));
            throw new AssertionError($"{dependency} never received {operation}; it received [{seen}]");
        }
        if (expected is null)
        {
            return;
        }
        var problems = new List<string>();
        foreach (var request in requests)
        {
            try
            {
                Compare.AssertSubset(request, expected, $"{dependency} {operation}");
                return;
            }
            catch (AssertionError error)
            {
                problems.Add(error.Message);
            }
        }
        throw new AssertionError(string.Join("; ", problems));
    }
}
