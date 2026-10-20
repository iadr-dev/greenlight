using Greenlight.Tests.Drivers;
using Reqnroll;

namespace Greenlight.Tests.Steps;

/// <summary>
/// The core instructions of greenlight's step vocabulary, bound to the drivers.
///
/// Each step carries the id of the instruction it implements in a `// C.…` comment; the adapter's contract test checks
/// that every instruction of the declared profiles is present. Steps only call drivers: no paths, no selectors, no SQL
/// here. Project-specific steps that compose these live in their own class (ProjectSteps.cs).
///
/// Reqnroll picks a binding by its signature as well as its expression, so a step that accepts a data table or a doc
/// string has one method for each shape (without argument, with a DataTable, with a string). Expressions must not
/// overlap: a step that matches two expressions is an ambiguous-binding failure.
/// </summary>
[Binding]
public sealed class CoreSteps(World world)
{
    // -- Given -------------------------------------------------------------------------------------

    [Given(@"^the following (.+) exist:$")] // C.ENTITY.SEED
    public void EntitiesExist(string entity, DataTable table)
    {
        world.Track(entity);
        world.System.Seed(entity, Compare.Rows(table));
    }

    [Given(@"^(.+) is signed in as (.+)$")] // C.ACTOR.AUTH
    public void ActorSignedIn(string actor, string role) => world.Headers[actor] = world.System.Authenticate(actor, role);

    [Given(@"^the current time is (.+)$")] // C.CLOCK.SET
    public void TimeIs(string moment) => world.Clock.Set(moment);

    [Given(@"^(.+) responds to (.+) with:$")] // C.STUB.RESPOND
    public void DependencyResponds(string dependency, string operation, DataTable table) =>
        world.Stubs.Respond(dependency, operation, Compare.Payload(table, null));

    [Given(@"^(.+) responds to (.+) with:$")] // C.STUB.RESPOND
    public void DependencyResponds(string dependency, string operation, string text) =>
        world.Stubs.Respond(dependency, operation, Compare.Payload(null, text));

    [Given(@"^the (.+) feature flag is (on|off)$")] // C.FLAG.SET
    public void FlagIs(string flag, string state) => world.System.SetFlag(flag, state == "on");

    [Given(@"^the input file (.+) contains:$")] // C.FILE.GIVEN
    public void InputFile(string file, DataTable table) => world.Workspace.Write(file, Compare.TextOf(table, null));

    [Given(@"^the input file (.+) contains:$")] // C.FILE.GIVEN
    public void InputFile(string file, string text) => world.Workspace.Write(file, Compare.TextOf(null, text));

    // -- When --------------------------------------------------------------------------------------

    [When(@"^the (.+) event is received with:$")] // C.EVENT.RECEIVE
    public void EventReceived(string name, DataTable table) => DeliverEvent(name, Compare.Payload(table, null));

    [When(@"^the (.+) event is received with:$")] // C.EVENT.RECEIVE
    public void EventReceived(string name, string text) => DeliverEvent(name, Compare.Payload(null, text));

    [When(@"^the (.+) job runs$")] // C.JOB.RUN
    public void JobRuns(string job)
    {
        world.Act();
        world.System.RunJob(job);
    }

    [When(@"^(.+) is called with:$")] // C.LIB.CALL
    public void LibCall(string operation, DataTable table) => CallLib(operation, Compare.Payload(table, null));

    [When(@"^(.+) is called with:$")] // C.LIB.CALL
    public void LibCall(string operation, string text) => CallLib(operation, Compare.Payload(null, text));

    [When(@"^(.+) calls (.+?)(?: with:)?$")] // C.API.CALL
    public void ApiCall(string actor, string operation) => CallApi(actor, operation, null);

    [When(@"^(.+) calls (.+?)(?: with:)?$")] // C.API.CALL
    public void ApiCall(string actor, string operation, DataTable table) => CallApi(actor, operation, Compare.Payload(table, null));

    [When(@"^(.+) calls (.+?)(?: with:)?$")] // C.API.CALL
    public void ApiCall(string actor, string operation, string text) => CallApi(actor, operation, Compare.Payload(null, text));

    [When(@"^(.+) runs (.+?)(?: with:)?$")] // C.CLI.RUN
    public void CliRun(string actor, string command) => RunCli(command, null);

    [When(@"^(.+) runs (.+?)(?: with:)?$")] // C.CLI.RUN
    public void CliRun(string actor, string command, DataTable table) => RunCli(command, table);

    [When(@"^(.+) passes$")] // C.CLOCK.ADVANCE
    public void TimePasses(string duration) => world.Clock.Advance(duration);

    // -- Then --------------------------------------------------------------------------------------

    [Then(@"^the request succeeds$")] // C.API.STATUS
    public void RequestSucceeds() => Api.AssertSucceeds(world);

    [Then(@"^the request is rejected with (.+)$")] // C.API.STATUS
    public void RequestRejected(string error) => Api.AssertRejected(world, error);

    [Then(@"^the response contains:$")] // C.API.BODY
    public void ResponseContains(DataTable table) => Compare.AssertSubset(world.Last("api").Body, Compare.Payload(table, null), "the response");

    [Then(@"^the response contains:$")] // C.API.BODY
    public void ResponseContains(string text) => Compare.AssertSubset(world.Last("api").Body, Compare.Payload(null, text), "the response");

    [Then(@"^the (.+) records (are|include):$")] // C.ENTITY.VERIFY
    public void RecordsVerified(string entity, string mode, DataTable table)
    {
        var actual = world.System.Records(entity);
        var expected = Compare.Rows(table);
        if (mode == "include")
        {
            Compare.AssertSubset(actual, expected, $"the {entity} records");
        }
        else
        {
            Compare.AssertSameRecords(actual, expected, $"the {entity} records");
        }
    }

    [Then(@"^no (.+) records changed$")] // C.ENTITY.UNCHANGED
    public void RecordsUnchanged(string entity) => world.AssertUnchanged(entity);

    [Then(@"^(.+) ran at most (\d+) queries$")] // C.QUERY.COUNT
    public void QueriesAtMost(string operation, int count) => world.AssertQueriesAtMost(operation, count);

    [Then(@"^the (.+) event is published with:$")] // C.EVENT.PUBLISHED
    public void EventPublished(string name, DataTable table) => AssertPublished(name, Compare.Payload(table, null));

    [Then(@"^the (.+) event is published with:$")] // C.EVENT.PUBLISHED
    public void EventPublished(string name, string text) => AssertPublished(name, Compare.Payload(null, text));

    [Then(@"^(.+) received (.+) with:$")] // C.STUB.CALLED
    public void DependencyReceived(string dependency, string operation, DataTable table) =>
        world.Stubs.AssertReceived(dependency, operation, Compare.Payload(table, null));

    [Then(@"^(.+) received (.+) with:$")] // C.STUB.CALLED
    public void DependencyReceived(string dependency, string operation, string text) =>
        world.Stubs.AssertReceived(dependency, operation, Compare.Payload(null, text));

    [Then(@"^the command succeeds$")] // C.CLI.RESULT
    public void CommandSucceeds() => Cli.AssertSucceeds(world);

    [Then(@"^the command fails with (.+)$")] // C.CLI.RESULT
    public void CommandFails(string error) => Cli.AssertFails(world, error);

    [Then(@"^the (stdout|stderr) output contains:$")] // C.OUTPUT.CONTAINS
    public void OutputContains(string stream, DataTable table) => AssertOutput(stream, Compare.TextOf(table, null));

    [Then(@"^the (stdout|stderr) output contains:$")] // C.OUTPUT.CONTAINS
    public void OutputContains(string stream, string text) => AssertOutput(stream, Compare.TextOf(null, text));

    [Then(@"^the output file (.+) contains:$")] // C.FILE.VERIFY
    public void OutputFileContains(string file, DataTable table) => world.Workspace.AssertContains(file, Compare.TextOf(table, null));

    [Then(@"^the output file (.+) contains:$")] // C.FILE.VERIFY
    public void OutputFileContains(string file, string text) => world.Workspace.AssertContains(file, Compare.TextOf(null, text));

    [Then(@"^the result is:$")] // C.LIB.RESULT
    public void ResultIs(DataTable table) => Lib.AssertResult(world, Compare.Payload(table, null), exact: true);

    [Then(@"^the result is:$")] // C.LIB.RESULT
    public void ResultIs(string text) => Lib.AssertResult(world, Compare.Payload(null, text), exact: true);

    [Then(@"^the result includes:$")] // C.LIB.RESULT
    public void ResultIncludes(DataTable table) => Lib.AssertResult(world, Compare.Payload(table, null), exact: false);

    [Then(@"^the result includes:$")] // C.LIB.RESULT
    public void ResultIncludes(string text) => Lib.AssertResult(world, Compare.Payload(null, text), exact: false);

    [Then(@"^the call fails with (.+)$")] // C.LIB.RESULT
    public void CallFails(string error) => Lib.AssertFails(world, error);

    // -- shared by the variants above ----------------------------------------------------------------

    private void DeliverEvent(string name, System.Text.Json.Nodes.JsonNode? payload)
    {
        world.Act();
        world.System.DeliverEvent(name, payload);
    }

    private void CallLib(string operation, System.Text.Json.Nodes.JsonNode? payload)
    {
        world.Act();
        Lib.Call(world, operation, payload);
    }

    private void CallApi(string actor, string operation, System.Text.Json.Nodes.JsonNode? payload)
    {
        world.Act();
        Api.Call(world, actor, operation, payload);
    }

    private void RunCli(string command, DataTable? table)
    {
        world.Act();
        Cli.Run(world, command, table);
    }

    private void AssertPublished(string name, System.Text.Json.Nodes.JsonNode? payload) =>
        Compare.AssertSubset(world.System.Published(name), new System.Text.Json.Nodes.JsonArray(payload?.DeepClone()), $"the {name} events");

    private void AssertOutput(string stream, string expected)
    {
        var outcome = world.Last("cli");
        Compare.AssertTextContains(stream == "stderr" ? outcome.Stderr : outcome.Stdout, expected, $"the {stream} output");
    }
}
