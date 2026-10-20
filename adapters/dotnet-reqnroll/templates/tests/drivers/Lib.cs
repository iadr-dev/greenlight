using System.Text.Json.Nodes;

namespace Greenlight.Tests.Drivers;

/// <summary>Calling a public function by its logical name; the returned value or the thrown exception is kept.</summary>
public static class Lib
{
    public static void Call(World world, string operation, JsonNode? data)
    {
        if (!Operations.Lib.TryGetValue(operation, out var function))
        {
            throw new NotMapped("library operation", operation, Operations.Lib.Keys); // an unmapped function is a failure, not a result
        }
        try
        {
            world.Outcome = new Outcome("lib") { Body = Compare.Normal(function(data)), Operation = operation };
        }
        catch (Exception error) when (error is not ExpectedMissingException and not NotMapped)
        {
            world.Outcome = new Outcome("lib") { Error = error, Operation = operation }; // the scenario decides whether it was wanted
        }
    }

    public static void AssertResult(World world, JsonNode? expected, bool exact)
    {
        var outcome = world.Last("lib");
        if (outcome.Error is not null)
        {
            throw new AssertionError($"the call threw {outcome.Error.GetType().Name}: {outcome.Error.Message}");
        }
        if (exact)
        {
            Compare.AssertEqual(outcome.Body, expected, "the result");
        }
        else
        {
            Compare.AssertSubset(outcome.Body, expected, "the result");
        }
    }

    public static void AssertFails(World world, string error)
    {
        var outcome = world.Last("lib");
        if (outcome.Error is null)
        {
            throw new AssertionError($"the call should fail but returned {Compare.Show(outcome.Body)}");
        }
        if (!outcome.MatchesError(error))
        {
            throw new AssertionError($"the call failed, but not with '{error}': {outcome.Error.GetType().Name}: {outcome.Error.Message}");
        }
    }
}
