using System.Text.Json.Nodes;

namespace Greenlight.Tests.Drivers;

/// <summary>
/// The seams into the system under test. This is the one file of drivers that is specific to the project.
///
/// Every method says what it does and throws ExpectedMissingException until the project implements the seam: during
/// the red phase that is the right failure. Use the most realistic seam available: the HTTP client of an in-memory
/// host first (for ASP.NET, WebApplicationFactory), then a domain service, then a repository, then the raw database.
/// Add the fields you need (a factory, a database, a counter).
/// </summary>
public class SystemUnderTest(Clock clock, Stubs stubs) : IDisposable
{
    /// <summary>The scenario's clock: give the application a clock seam that reads it.</summary>
    protected Clock Clock { get; } = clock;

    /// <summary>The scenario's stubbed dependencies: route the application's outbound calls through them.</summary>
    protected Stubs Stubs { get; } = stubs;

    // -- Given -------------------------------------------------------------------------------------

    /// <summary>Create rows of an entity. An unknown column is an error.</summary>
    public virtual void Seed(string entity, IReadOnlyList<JsonObject> rows) =>
        throw new ExpectedMissingException($"a way to create {entity} records");

    /// <summary>Sign the actor in with the role and return the HTTP headers that prove it.</summary>
    public virtual IReadOnlyDictionary<string, string> Authenticate(string actor, string role) =>
        throw new ExpectedMissingException($"a way to sign in as {role}");

    /// <summary>Configure a feature flag or setting.</summary>
    public virtual void SetFlag(string flag, bool enabled) =>
        throw new ExpectedMissingException($"the {flag} feature flag");

    // -- When --------------------------------------------------------------------------------------

    /// <summary>An HTTP client for the application. Requests are served in memory, so no port is opened.</summary>
    public virtual HttpClient Http() =>
        throw new ExpectedMissingException("an HTTP client for the application");

    /// <summary>Hand an event to the application.</summary>
    public virtual void DeliverEvent(string name, JsonNode? payload) =>
        throw new ExpectedMissingException($"a way to deliver the {name} event");

    /// <summary>Run a scheduled job once.</summary>
    public virtual void RunJob(string job) =>
        throw new ExpectedMissingException($"the {job} job");

    /// <summary>
    /// Fill in request fields the scenario did not give, for example the id of the order created earlier, so a step
    /// like `alice calls look up order` needs no id. The default adds nothing.
    /// </summary>
    public virtual JsonObject Complete(string operation, JsonObject fields) => fields;

    // -- Then --------------------------------------------------------------------------------------

    /// <summary>Every stored record of an entity, read through a seam that does not change anything.</summary>
    public virtual IReadOnlyList<JsonObject> Records(string entity) =>
        throw new ExpectedMissingException($"a way to read {entity} records");

    /// <summary>
    /// How many database statements have run since the scenario began. Install a QueryCounter (see Queries.cs) on the
    /// application's data access when the system is built and return its Count. Only scenarios that check a query count
    /// need this seam.
    /// </summary>
    public virtual int QueriesExecuted() =>
        throw new ExpectedMissingException("a counter of the application's database statements");

    /// <summary>The payloads of an event that the application published (a test double of the broker).</summary>
    public virtual IReadOnlyList<JsonNode?> Published(string name) =>
        throw new ExpectedMissingException($"a captured {name} event");

    /// <summary>Called after every scenario: drop data, close clients.</summary>
    public virtual void Dispose() => GC.SuppressFinalize(this);
}
