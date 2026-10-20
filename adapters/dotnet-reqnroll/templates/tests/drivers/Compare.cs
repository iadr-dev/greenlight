using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Reqnroll;

namespace Greenlight.Tests.Drivers;

/// <summary>Turning Gherkin tables and doc strings into data, and comparing data the way the instructions say.</summary>
public static partial class Compare
{
    /// <summary>A cell or doc string as data: JSON when it parses (numbers, true, null, lists, objects), else the text.</summary>
    public static JsonNode? ParseValue(string text)
    {
        text = text.Trim();
        try
        {
            return JsonNode.Parse(text);
        }
        catch (Exception error) when (error is JsonException or ArgumentException)
        {
            return JsonValue.Create(text);
        }
    }

    /// <summary>A table with a header row as a list of records.</summary>
    public static List<JsonObject> Rows(DataTable? table)
    {
        var rows = new List<JsonObject>();
        if (table is null)
        {
            return rows;
        }
        var header = table.Header.ToList();
        foreach (var row in table.Rows)
        {
            var record = new JsonObject();
            for (var column = 0; column < header.Count; column++)
            {
                record[header[column]] = ParseValue(row[column]);
            }
            rows.Add(record);
        }
        return rows;
    }

    /// <summary>The data a step carries: a doc string as JSON or text, or a table (one row becomes an object).</summary>
    public static JsonNode? Payload(DataTable? table, string? text)
    {
        if (text is not null)
        {
            return ParseValue(text);
        }
        var rows = Rows(table);
        return rows.Count switch
        {
            0 => null,
            1 => rows[0],
            _ => new JsonArray(rows.Select(row => (JsonNode?)row.DeepClone()).ToArray()),
        };
    }

    /// <summary>The step's doc string, or its table with comma-separated rows.</summary>
    public static string TextOf(DataTable? table, string? text)
    {
        if (text is not null)
        {
            return text;
        }
        if (table is null)
        {
            return "";
        }
        var lines = new List<string> { string.Join(",", table.Header) };
        lines.AddRange(table.Rows.Select(row => string.Join(",", Enumerable.Range(0, table.Header.Count).Select(i => row[i]))));
        return string.Join("\n", lines);
    }

    /// <summary>Whatever the project's code returned, as JSON data that compares the same way as what a scenario wrote.</summary>
    public static JsonNode? Normal(object? value) =>
        JsonNode.Parse(value is JsonNode node ? node.ToJsonString() : JsonSerializer.Serialize(value)); // one representation for every number

    /// <summary>Line endings, trailing blanks and blank lines do not matter.</summary>
    public static string NormaliseText(string text) =>
        string.Join("\n", text.Replace("\r\n", "\n").Trim().Split('\n')
            .Where(line => line.Trim().Length > 0).Select(line => line.TrimEnd()));

    public static string Show(JsonNode? node) => node?.ToJsonString() ?? "null";

    public static void AssertEqual(object? actual, object? expected, string what)
    {
        if (!SameData(Normal(actual), Normal(expected)))
        {
            throw new AssertionError($"{what}: expected {Show(Normal(expected))} but got {Show(Normal(actual))}");
        }
    }

    /// <summary>The same records, in any order.</summary>
    public static void AssertSameRecords(IEnumerable<JsonObject> actual, IEnumerable<JsonObject> expected, string what)
    {
        static JsonArray Sorted(IEnumerable<JsonObject> rows) =>
            new(rows.OrderBy(row => Show(row), StringComparer.Ordinal).Select(row => (JsonNode?)row.DeepClone()).ToArray());
        AssertEqual(Sorted(actual), Sorted(expected), what);
    }

    /// <summary>Every field of expected is in actual (recursively); lists must contain each expected item.</summary>
    public static void AssertSubset(object? actual, object? expected, string what)
    {
        var problem = SubsetProblem(Normal(actual), Normal(expected), "");
        if (problem is not null)
        {
            throw new AssertionError($"{what}: {problem} (actual: {Show(Normal(actual))})");
        }
    }

    public static void AssertTextContains(string actual, string expected, string what)
    {
        var wanted = NormaliseText(expected);
        var got = NormaliseText(actual);
        if (!got.Contains(wanted, StringComparison.Ordinal))
        {
            throw new AssertionError($"{what} does not contain '{wanted}'; it is '{got}'");
        }
    }

    private static bool SameData(JsonNode? left, JsonNode? right)
    {
        switch (left, right)
        {
            case (null, null):
                return true;
            case (JsonObject a, JsonObject b):
                return a.Count == b.Count && a.All(pair => b.TryGetPropertyValue(pair.Key, out var other) && SameData(pair.Value, other));
            case (JsonArray a, JsonArray b):
                return a.Count == b.Count && a.Zip(b).All(pair => SameData(pair.First, pair.Second));
            case (JsonValue a, JsonValue b):
                return SameScalar(a, b);
            default:
                return false;
        }
    }

    private static bool SameScalar(JsonValue left, JsonValue right)
    {
        if (left.GetValueKind() == JsonValueKind.Number && right.GetValueKind() == JsonValueKind.Number)
        {
            return left.GetValue<decimal>() == right.GetValue<decimal>();
        }
        return left.GetValueKind() == right.GetValueKind() && left.ToJsonString() == right.ToJsonString();
    }

    private static string Join(string path, string key) => path.Length == 0 ? key : $"{path}.{key}";

    private static string Named(string path) => path.Length == 0 ? "value" : path;

    private static string? SubsetProblem(JsonNode? actual, JsonNode? expected, string path)
    {
        switch (expected)
        {
            case JsonObject want:
                if (actual is not JsonObject have)
                {
                    return $"{Named(path)} should be an object";
                }
                foreach (var (key, value) in want.OrderBy(pair => pair.Key, StringComparer.Ordinal))
                {
                    if (!have.TryGetPropertyValue(key, out var found))
                    {
                        return $"{Join(path, key)} is missing";
                    }
                    var problem = SubsetProblem(found, value, Join(path, key));
                    if (problem is not null)
                    {
                        return problem;
                    }
                }
                return null;
            case JsonArray items:
                if (actual is not JsonArray candidates)
                {
                    return $"{Named(path)} should be a list";
                }
                foreach (var item in items)
                {
                    if (!candidates.Any(candidate => SubsetProblem(candidate, item, path) is null))
                    {
                        return $"{Named(path)} has no item matching {Show(item)}";
                    }
                }
                return null;
            default:
                return SameData(actual, expected) ? null : $"{Named(path)} is {Show(actual)}, expected {Show(expected)}";
        }
    }

    [GeneratedRegex(@"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d|weeks?|w)\b", RegexOptions.IgnoreCase)]
    private static partial Regex DurationPattern();

    /// <summary>'2 days', '30 minutes' or '1h 30m' as seconds.</summary>
    public static double DurationSeconds(string text)
    {
        var found = DurationPattern().Matches(text);
        var rest = DurationPattern().Replace(text, "").Trim(' ', ',');
        if (found.Count == 0 || rest.Replace("and", "", StringComparison.OrdinalIgnoreCase).Trim().Length > 0)
        {
            throw new AssertionError($"cannot read the duration '{text}'");
        }
        return found.Sum(match =>
        {
            var number = double.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture);
            var unit = char.ToLowerInvariant(match.Groups[2].Value[0]);
            return number * unit switch { 's' => 1, 'm' => 60, 'h' => 3600, 'd' => 86400, _ => 604800 };
        });
    }
}
