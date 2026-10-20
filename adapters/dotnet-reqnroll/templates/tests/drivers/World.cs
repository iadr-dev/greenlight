using System.Text.Json.Nodes;

namespace Greenlight.Tests.Drivers;

/// <summary>What the last action did: an API response, a command, or a library call.</summary>
public sealed class Outcome(string kind)
{
    public string Kind { get; } = kind;                      // api | cli | lib
    public int Status { get; init; }                         // api
    public JsonNode? Body { get; init; }                     // api: parsed body; lib: the returned value
    public int ExitCode { get; init; }                       // cli
    public string Stdout { get; init; } = "";                // cli
    public string Stderr { get; init; } = "";                // cli
    public Exception? Error { get; init; }                   // lib: the exception the call threw
    public string Operation { get; init; } = "";             // api, lib: the logical name that was called

    /// <summary>Is this outcome the logical error <paramref name="name"/> (see Operations.Errors)?</summary>
    public bool MatchesError(string name)
    {
        if (!Operations.Errors.TryGetValue(name, out var rule))
        {
            throw new NotMapped("error", name, Operations.Errors.Keys);
        }
        var text = string.Join(" ", new[] { Compare.Show(Body), Stderr, Stdout, Error?.Message ?? "" }).ToLowerInvariant();
        var checks = new[]
        {
            rule.Statuses is null || rule.Statuses.Contains(Status),
            rule.ExceptionType is null || Error?.GetType().Name == rule.ExceptionType,
            rule.ExitCode is null || rule.ExitCode == ExitCode,
            rule.Text is null || text.Contains(rule.Text.ToLowerInvariant(), StringComparison.Ordinal),
        };
        return checks.All(check => check) && (rule.Statuses is not null || rule.ExceptionType is not null || rule.ExitCode is not null || rule.Text is not null);
    }
}

/// <summary>
/// Everything one scenario knows. Reqnroll makes a fresh World for every scenario and hands the same one to every step
/// class of that scenario, so nothing leaks between scenarios.
/// </summary>
public sealed class World : IDisposable
{
    private readonly HashSet<string> _tracked = [];
    private Dictionary<string, List<JsonObject>>? _before;
    private int? _queriesBefore;

    public World()
    {
        Clock = new Clock();
        Stubs = new Stubs();
        Workspace = new Workspace(Directory.CreateTempSubdirectory("greenlight-scenario-").FullName);
        System = Wiring.CreateSystem(Clock, Stubs);
    }

    public SystemUnderTest System { get; }
    public Clock Clock { get; }
    public Stubs Stubs { get; }
    public Workspace Workspace { get; }
    public Dictionary<string, IReadOnlyDictionary<string, string>> Headers { get; } = [];
    public Outcome? Outcome { get; set; }

    public void Track(string entity) => _tracked.Add(entity);

    /// <summary>
    /// Called before every action: remember what every tracked entity looked like before the first one, and how many
    /// database statements had run before this one.
    /// </summary>
    public void Act()
    {
        _before ??= _tracked.ToDictionary(entity => entity, entity => System.Records(entity).Select(row => (JsonObject)row.DeepClone()).ToList());
        try
        {
            _queriesBefore = System.QueriesExecuted();
        }
        catch (ExpectedMissingException)
        {
            _queriesBefore = null; // only a scenario that counts needs the seam
        }
    }

    /// <summary>The last action ran at most <paramref name="limit"/> statements (an N+1 problem is a count that grows with the rows).</summary>
    public void AssertQueriesAtMost(string operation, int limit)
    {
        if (Outcome is { Operation.Length: > 0 } && Outcome.Operation != operation)
        {
            throw new AssertionError($"the last action was '{Outcome.Operation}', not '{operation}'");
        }
        var total = System.QueriesExecuted(); // throws ExpectedMissingException without a counter
        if (_queriesBefore is null)
        {
            throw new AssertionError("no action ran before this check: a When step has to run first");
        }
        var ran = total - _queriesBefore.Value;
        if (ran > limit)
        {
            throw new AssertionError($"{operation} ran {ran} queries, more than the {limit} allowed (a count that grows with the number of records is an N+1 problem)");
        }
    }

    public void AssertUnchanged(string entity)
    {
        if (_before is null || !_before.TryGetValue(entity, out var before))
        {
            throw new AssertionError($"{entity} records were not tracked: seed them in a Given step (the following {entity} exist:) so that their state can be compared");
        }
        Compare.AssertSameRecords(System.Records(entity), before, $"the {entity} records");
    }

    /// <summary>The outcome of the last action, which must be of the given kind.</summary>
    public Outcome Last(string kind)
    {
        if (Outcome is null)
        {
            throw new AssertionError($"there is no result yet: a When step ({kind}) has to run first");
        }
        if (Outcome.Kind != kind)
        {
            throw new AssertionError($"the last action was {Outcome.Kind}, not {kind}");
        }
        return Outcome;
    }

    public void Dispose()
    {
        System.Dispose();
        Clock.Stop();
        Workspace.Delete();
        GC.SuppressFinalize(this);
    }
}
