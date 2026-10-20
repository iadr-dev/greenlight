using System.Globalization;

namespace Greenlight.Tests.Drivers;

/// <summary>
/// The injected clock. Application code reads world.Clock.Now (give it a clock seam, for example a TimeProvider);
/// nothing freezes the process clock. Note the seam in system.md.
/// </summary>
public sealed class Clock : TimeProvider
{
    private DateTimeOffset? _now;

    /// <summary>Freeze the clock at the given moment (UTC when no zone is given).</summary>
    public void Set(string text)
    {
        if (!DateTimeOffset.TryParse(text.Trim(), CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var moment))
        {
            throw new AssertionError($"cannot read the time '{text}' (use 2026-03-01T09:00:00Z or 2026-03-01)");
        }
        _now = moment;
    }

    /// <summary>Move the frozen clock on.</summary>
    public void Advance(string text)
    {
        if (_now is null)
        {
            throw new AssertionError("set the current time first (Given the current time is ...)");
        }
        _now = _now.Value.AddSeconds(Compare.DurationSeconds(text));
    }

    /// <summary>The frozen moment, or the real time when none was set.</summary>
    public DateTimeOffset Now => _now ?? DateTimeOffset.UtcNow;

    public override DateTimeOffset GetUtcNow() => Now;

    public void Stop() => _now = null;
}
