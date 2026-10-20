using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Greenlight.Tests.Drivers;

/// <summary>Calling an API operation by its logical name and judging the response by logical result.</summary>
public static class Api
{
    public static void Call(World world, string actor, string operation, JsonNode? data)
    {
        if (!Operations.Api.TryGetValue(operation, out var route))
        {
            throw new NotMapped("API operation", operation, Operations.Api.Keys);
        }
        var client = world.System.Http();
        var given = data as JsonObject ?? [];
        var fields = world.System.Complete(operation, (JsonObject)given.DeepClone()); // the project may add what the scenario left out
        var path = route.Path;
        var sent = new JsonObject();
        foreach (var (name, value) in fields.ToList())
        {
            var placeholder = "{" + name + "}";
            if (path.Contains(placeholder, StringComparison.Ordinal))
            {
                path = path.Replace(placeholder, Uri.EscapeDataString(TextOf(value)), StringComparison.Ordinal);
            }
            else
            {
                sent[name] = value?.DeepClone();
            }
        }
        var method = new HttpMethod(route.Method.ToUpperInvariant());
        if (method == HttpMethod.Get && sent.Count > 0)
        {
            path += "?" + string.Join("&", sent.Select(pair => $"{Uri.EscapeDataString(pair.Key)}={Uri.EscapeDataString(TextOf(pair.Value))}"));
        }
        using var request = new HttpRequestMessage(method, path);
        if (method != HttpMethod.Get)
        {
            var body = data is not null and not JsonObject ? data : sent.Count > 0 ? sent : null;
            if (body is not null)
            {
                request.Content = new StringContent(body.ToJsonString(), Encoding.UTF8, MediaTypeHeaderValue.Parse("application/json"));
            }
        }
        if (world.Headers.TryGetValue(actor, out var headers))
        {
            foreach (var (name, value) in headers)
            {
                request.Headers.TryAddWithoutValidation(name, value);
            }
        }
        using var response = client.SendAsync(request).GetAwaiter().GetResult(); // works with every handler, in-memory ones included
        var text = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        world.Outcome = new Outcome("api") { Status = (int)response.StatusCode, Body = Compare.ParseValue(text), Operation = operation };
    }

    private static string TextOf(JsonNode? value) =>
        value is JsonValue scalar && scalar.TryGetValue<string>(out var text) ? text : value?.ToJsonString() ?? "";

    public static void AssertSucceeds(World world)
    {
        var outcome = world.Last("api");
        if (outcome.Status is < 200 or >= 300)
        {
            throw new AssertionError($"the request should succeed but got status {outcome.Status}: {Compare.Show(outcome.Body)}");
        }
    }

    public static void AssertRejected(World world, string error)
    {
        var outcome = world.Last("api");
        if (outcome.Status < 400)
        {
            throw new AssertionError($"the request should be rejected but got status {outcome.Status}");
        }
        if (!outcome.MatchesError(error))
        {
            throw new AssertionError($"the request was rejected, but not with '{error}': status {outcome.Status}, {Compare.Show(outcome.Body)}");
        }
    }
}
