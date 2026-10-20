namespace Greenlight.Tests.Drivers;

/// <summary>
/// Counts the database statements an action runs, so that an N+1 problem is a failing scenario. Create one when the
/// project's SystemUnderTest is built, call Record from the application's data access (an EF Core
/// DbCommandInterceptor, a Dapper or ADO.NET wrapper, the repository itself), and return Count from
/// SystemUnderTest.QueriesExecuted.
/// </summary>
public sealed class QueryCounter
{
    // Transaction control says nothing about the data read, so it is not counted.
    private static readonly string[] Ignored = ["SAVEPOINT", "RELEASE SAVEPOINT", "ROLLBACK TO SAVEPOINT", "BEGIN", "COMMIT", "ROLLBACK"];

    private int _count;

    public int Count => Volatile.Read(ref _count);

    public void Record(string statement)
    {
        var text = statement.TrimStart();
        if (!Ignored.Any(prefix => text.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)))
        {
            Interlocked.Increment(ref _count);
        }
    }
}
