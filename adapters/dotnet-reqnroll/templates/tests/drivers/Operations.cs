using System.Text.Json.Nodes;
using Greenlight.Tests.Sample;

namespace Greenlight.Tests.Drivers;

/// <summary>An API operation: the method and the path, which may contain {field}, filled from the request data.</summary>
public sealed record Route(string Method, string Path);

/// <summary>What a logical error looks like. Any field that is set must match.</summary>
public sealed record ErrorRule(
    int[]? Statuses = null,         // HTTP status codes
    string? ExceptionType = null,   // the simple name of the exception class
    int? ExitCode = null,           // process exit code
    string? Text = null);           // text in the response body, stderr or the exception message

/// <summary>
/// The map from the logical names used in features to this system. Features never contain paths, binaries or type
/// names. The step-engineer fills this in from the system map (system.md); the sample entries belong to the sample
/// feature and can be deleted with it.
/// </summary>
public static class Operations
{
    public static readonly Dictionary<string, Route> Api = new()
    {
        // ["place order"] = new("POST", "/orders"),
    };

    /// <summary>A command line (program and arguments), started in the scenario workspace.</summary>
    public static readonly Dictionary<string, string[]> Commands = new()
    {
        // ["export report"] = ["dotnet", "run", "--project", "src/Report", "--"],
    };

    /// <summary>A public function. The data of the step arrives as JSON (an object for a table row); return the result or throw.</summary>
    public static readonly Dictionary<string, Func<JsonNode?, object?>> Lib = new()
    {
        ["add"] = input => Calculator.Add(input!["a"]!.GetValue<int>(), input["b"]!.GetValue<int>()), // sample
    };

    /// <summary>A file name relative to the scenario workspace.</summary>
    public static readonly Dictionary<string, string> Files = new()
    {
        // ["report"] = "out/report.txt",
    };

    public static readonly Dictionary<string, ErrorRule> Errors = new()
    {
        ["negative input"] = new(ExceptionType: nameof(NegativeInputException)), // sample
        // ["validation error"] = new(Statuses: [400, 422]),
    };
}
