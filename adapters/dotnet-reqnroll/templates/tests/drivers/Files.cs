namespace Greenlight.Tests.Drivers;

/// <summary>An isolated directory per scenario, with files addressed by logical name.</summary>
public sealed class Workspace(string root)
{
    public string Root { get; } = root;

    private string PathOf(string name)
    {
        if (!Operations.Files.TryGetValue(name, out var relative))
        {
            throw new NotMapped("file", name, Operations.Files.Keys);
        }
        var target = Path.GetFullPath(Path.Combine(Root, relative));
        if (!target.StartsWith(Path.GetFullPath(Root) + Path.DirectorySeparatorChar, StringComparison.Ordinal))
        {
            throw new AssertionError($"'{name}' maps outside the workspace");
        }
        return target;
    }

    public void Write(string name, string content)
    {
        var target = PathOf(name);
        Directory.CreateDirectory(Path.GetDirectoryName(target)!);
        File.WriteAllText(target, content);
    }

    public string Read(string name)
    {
        var target = PathOf(name);
        return File.Exists(target)
            ? File.ReadAllText(target)
            : throw new AssertionError($"the file '{name}' ({Operations.Files[name]}) was not produced");
    }

    public void AssertContains(string name, string expected) =>
        Compare.AssertTextContains(Read(name), expected, $"file '{name}'");

    public void Delete()
    {
        if (Directory.Exists(Root))
        {
            Directory.Delete(Root, recursive: true);
        }
    }
}
