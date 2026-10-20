using Greenlight.Tests.Drivers;
using Reqnroll;

namespace Greenlight.Tests.Steps;

/// <summary>
/// The steps of this project: phrases composed from the core instructions (see .bdd/vocabulary.toml) that call the same
/// drivers. It is empty at first. An expression here must not also match a core one, or Reqnroll reports the step as
/// ambiguous.
/// </summary>
[Binding]
public sealed class ProjectSteps(World world)
{
    public World World { get; } = world;
}
