namespace Greenlight.Tests.Drivers;

/// <summary>Makes the system of one scenario. Return your own subclass of SystemUnderTest here.</summary>
public static class Wiring
{
    public static SystemUnderTest CreateSystem(Clock clock, Stubs stubs) => new(clock, stubs);
}
