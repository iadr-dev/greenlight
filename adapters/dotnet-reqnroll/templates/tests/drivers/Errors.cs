namespace Greenlight.Tests.Drivers;

/// <summary>The marker the red gate classifies on: a failure that contains it is an expected failure.</summary>
public static class Marker
{
    public const string Text = "BDD_EXPECTED_MISSING";
}

/// <summary>The system under test does not have this yet. During the red phase that is the right failure.</summary>
public sealed class ExpectedMissingException(string what)
    : Exception($"{Marker.Text}: {what} does not exist yet");

/// <summary>An assertion that did not hold.</summary>
public sealed class AssertionError(string message) : Exception($"AssertionError: {message}");

/// <summary>The system called an external dependency that the scenario did not stub.</summary>
public sealed class UnstubbedCall(string dependency, string operation)
    : Exception($"UnstubbedCall: {dependency} was asked to {operation} but the scenario did not stub it");

/// <summary>A real network connection was attempted. Stub the dependency instead.</summary>
public sealed class OutboundNetworkBlocked(string address)
    : Exception($"OutboundNetworkBlocked: a real connection to {address} was attempted; stub the dependency instead");

/// <summary>
/// A defect of the test, not a missing feature: a logical name in a feature has no entry in Operations.cs.
/// </summary>
public sealed class NotMapped(string kind, string name, IEnumerable<string> known)
    : Exception($"NotMapped: no {kind} named '{name}' in tests/drivers/Operations.cs (known: [{string.Join(", ", known.Order())}])");
