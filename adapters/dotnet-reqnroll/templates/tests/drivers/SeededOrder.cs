using System.Security.Cryptography;
using System.Text;
using Xunit;
using Xunit.Abstractions;
using Xunit.Sdk;

[assembly: TestCaseOrderer("Greenlight.Tests.Drivers.SeededCaseOrderer", "GreenlightTests")]
[assembly: TestCollectionOrderer("Greenlight.Tests.Drivers.SeededCollectionOrderer", "GreenlightTests")]

namespace Greenlight.Tests.Drivers;

/// <summary>
/// `bdd run --shuffle --seed N` sets GREENLIGHT_BDD_SEED: the scenarios then run in an order made repeatable by the
/// seed. Without it the order is xUnit's own.
/// </summary>
internal static class Seed
{
    private static readonly string? Value = Environment.GetEnvironmentVariable("GREENLIGHT_BDD_SEED");

    public static IEnumerable<T> Order<T>(IEnumerable<T> items, Func<T, string> name) =>
        Value is null
            ? items
            : items.OrderBy(item => BitConverter.ToUInt64(SHA256.HashData(Encoding.UTF8.GetBytes(Value + name(item)))));
}

public sealed class SeededCaseOrderer : ITestCaseOrderer
{
    public IEnumerable<TTestCase> OrderTestCases<TTestCase>(IEnumerable<TTestCase> testCases) where TTestCase : ITestCase =>
        Seed.Order(testCases, testCase => testCase.DisplayName);
}

public sealed class SeededCollectionOrderer : ITestCollectionOrderer
{
    public IEnumerable<ITestCollection> OrderTestCollections(IEnumerable<ITestCollection> testCollections) =>
        Seed.Order(testCollections, collection => collection.DisplayName);
}
