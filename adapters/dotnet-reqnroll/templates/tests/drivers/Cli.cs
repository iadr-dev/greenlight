using System.Diagnostics;
using Reqnroll;

namespace Greenlight.Tests.Drivers;

/// <summary>
/// Running a command by its logical name in the scenario workspace. The table of a runs step has two columns, key and
/// value. Keys: arg (repeat for several arguments), stdin, and env.NAME.
/// </summary>
public static class Cli
{
    private static readonly TimeSpan Limit = TimeSpan.FromSeconds(60);

    public static void Run(World world, string command, DataTable? table)
    {
        if (!Operations.Commands.TryGetValue(command, out var words))
        {
            throw new NotMapped("command", command, Operations.Commands.Keys);
        }
        var start = new ProcessStartInfo(words[0])
        {
            WorkingDirectory = world.Workspace.Root,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        foreach (var word in words.Skip(1))
        {
            start.ArgumentList.Add(word);
        }
        var stdin = "";
        foreach (var row in table?.Rows ?? [])
        {
            var (key, value) = (row[0], row[1]);
            if (key == "arg")
            {
                start.ArgumentList.Add(value);
            }
            else if (key == "stdin")
            {
                stdin = value;
            }
            else if (key.StartsWith("env.", StringComparison.Ordinal))
            {
                start.Environment[key[4..]] = value;
            }
            else
            {
                throw new AssertionError($"unknown key '{key}' in the command table (use arg, stdin or env.NAME)");
            }
        }
        using var process = Process.Start(start) ?? throw new AssertionError($"the command '{command}' could not start");
        var output = process.StandardOutput.ReadToEndAsync();
        var errors = process.StandardError.ReadToEndAsync();
        process.StandardInput.Write(stdin);
        process.StandardInput.Close();
        if (!process.WaitForExit(Limit))
        {
            process.Kill(entireProcessTree: true);
            throw new AssertionError($"the command '{command}' took longer than {Limit.TotalSeconds:0} s");
        }
        world.Outcome = new Outcome("cli") { ExitCode = process.ExitCode, Stdout = output.GetAwaiter().GetResult(), Stderr = errors.GetAwaiter().GetResult() };
    }

    public static void AssertSucceeds(World world)
    {
        var outcome = world.Last("cli");
        if (outcome.ExitCode != 0)
        {
            throw new AssertionError($"the command should succeed but exited {outcome.ExitCode}: '{outcome.Stderr.Trim()}'");
        }
    }

    public static void AssertFails(World world, string error)
    {
        var outcome = world.Last("cli");
        if (outcome.ExitCode == 0)
        {
            throw new AssertionError("the command should fail but it succeeded");
        }
        if (!outcome.MatchesError(error))
        {
            throw new AssertionError($"the command failed, but not with '{error}': exit {outcome.ExitCode}, '{outcome.Stderr.Trim()}'");
        }
    }
}
