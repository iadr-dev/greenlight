# The step vocabulary

greenlight scenarios are written from a fixed, versioned set of **core instructions**. Each is a sentence pattern with
`{placeholders}`; the adapter binds it to a driver, so the same scenario text means the same thing in every project.
`bdd lint` rejects a step that matches no instruction (and any step that describes *how* instead of *what*:
clicks on selectors, SQL, URLs).

A project adds its own phrases in `.bdd/vocabulary.toml`, each composed from the core instructions, never as raw code.
The project glossary (`.bdd/glossary.md`) gives the domain words (entities, actors, roles, operations) that fill the
placeholders.

## Style warnings

Besides errors, `bdd lint` warns about the shape of a feature file. A warning never stops a gate or changes the exit
code; it is there so that the scenarios stay easy to read and to review.

| Code | Warns about |
|---|---|
| `L015` | steps out of order: Given, When, Then, each phase once (a second When/Then is a second scenario) |
| `L016` | a scenario with more than 10 steps |
| `L017` | placeholder data (`foo`, `bar`, `baz`, `lorem`, `asdf`, `xxx`, `test`) in steps or tables, unless the scenario is about invalid input (a title with "invalid", "malformed", "nonsense", "garbage" or "gibberish", or an `@invalid-input` tag) |
| `L018` | a `Background` that only one scenario uses |
| `L019` | a `Scenario Outline` with one example row, or rows that differ only in case or spacing |
| `L020` | a scenario with no title, or text under its title |
| `L021` | indentation that is not two spaces per level (a `Rule` adds a level; tabs are reported as tabs) |
| `L022` | a line longer than 120 characters (doc strings excepted) |
| `L023` | a blank line between two steps of one scenario |
| `L024` | no blank line between two scenarios that follow each other |
| `L025` | a file name that is not kebab-case |

A second `Feature` in one file and an `Or` step keyword stay parse errors (`L001`). A project can silence a style
warning it disagrees with, never an error, in `.bdd/config.toml`:

```toml
[lint]
ignore = ["L022", "L025"]
```

The `gherkin-style` card covers what the lint cannot judge: one behaviour per scenario, independent concerns kept apart,
state over navigation, a minimal `Given`, and `Scenario Outline` only for one behaviour with different inputs.

## Profiles

An adapter declares the profiles it supports; a project uses the instructions of those profiles.

| Profile | For |
|---|---|
| `base` | every project |
| `api` | HTTP/RPC services |
| `ui` | web, mobile and desktop UIs |
| `cli` | command-line tools and scripts |
| `lib` | libraries, SDKs and pure domain modules (shares the file instructions with cli) |
| `data` | services that store data in a database whose queries can be counted |

## Core instructions (version 2)

| ID | Kind | Profiles | Pattern | What it does |
|---|---|---|---|---|
| `C.ENTITY.SEED` | given | base | `the following {entity} exist:` | Create records via the most realistic seam (API, then domain service, then repository, then raw DB). Columns map to fields; unknown columns are an error. |
| `C.ACTOR.AUTH` | given | base | `{actor} is signed in as {role}` | Establish an authenticated session or token for a named actor. |
| `C.CLOCK.SET` | given | base | `the current time is {datetime}` | Freeze or inject time. All time-dependent steps use this clock. |
| `C.STUB.RESPOND` | given | base | `{dependency} responds to {operation} with:` | Stub an external dependency deterministically. Unstubbed external calls fail the scenario. |
| `C.FLAG.SET` | given | base | `the {flag} feature flag is {state:enum(on,off)}` | Configure a feature flag or setting for the scenario. |
| `C.STATE.GLOBAL` | given | ui | `the application state is:` | Initialize client-side global state or storage. |
| `C.FILE.GIVEN` | given | cli, lib | `the input file {file} contains:` | Create an input file in an isolated temporary workspace. {file} is a logical name; the real path is mapped in the system map. |
| `C.API.CALL` | when | api | `{actor} calls {operation} with:` | Invoke an API operation by logical name (mapped in the driver) and store the response. |
| `C.UI.OPEN` | when | ui | `{actor} opens the {page} page` | Navigate to a logical page. |
| `C.UI.ACT` | when | ui | `{actor} {action:enum(clicks,fills,selects,uploads,types,toggles)} {target}` | Perform a user action on a logical component. Selectors live in drivers, never in features. |
| `C.EVENT.RECEIVE` | when | base | `the {event} event is received with:` | Deliver an inbound message or webhook. |
| `C.JOB.RUN` | when | base | `the {job} job runs` | Execute a scheduled or background job synchronously. |
| `C.CLOCK.ADVANCE` | when | base | `{duration} passes` | Advance the injected clock. |
| `C.CLI.RUN` | when | cli | `{actor} runs {command}` | Run a logical command (args, env, stdin from the table) in the temporary workspace; capture exit code, stdout and stderr. Binary and flags are mapped in the driver. |
| `C.LIB.CALL` | when | lib | `{operation} is called with:` | Invoke a public function or method by logical name; capture the return value or the raised error. |
| `C.API.STATUS` | then | api | `the request succeeds` | Check the outcome by logical result, not raw HTTP codes (the driver maps them). |
| `C.API.BODY` | then | api | `the response contains:` | Subset match on fields; table rows for lists. |
| `C.ENTITY.VERIFY` | then | base | `the {entity} records are:` | Verify persisted state through a read seam. 'are' is the exact set, 'include' is a subset. |
| `C.ENTITY.UNCHANGED` | then | base | `no {entity} records changed` | Snapshot-compare. |
| `C.UI.SEE` | then | ui | `{actor} sees {target} showing:` | Visible state of a logical component (text, items, enabled or disabled). |
| `C.UI.NOT_SEE` | then | ui | `{actor} does not see {target}` | The logical component is not visible. |
| `C.STATE.VERIFY` | then | ui | `the application state includes:` | Client-side state check. |
| `C.EVENT.PUBLISHED` | then | base | `the {event} event is published with:` | Outbound message or event captured by a test double. |
| `C.STUB.CALLED` | then | base | `{dependency} received {operation} with:` | Verify an outbound call to a stubbed dependency. |
| `C.CLI.RESULT` | then | cli | `the command succeeds` | Check the outcome by logical result; the driver maps exit codes and messages. |
| `C.OUTPUT.CONTAINS` | then | cli | `the {stream:enum(stdout,stderr)} output contains:` | Match stdout or stderr with normalized line endings and whitespace; no regular expressions in features. |
| `C.FILE.VERIFY` | then | cli, lib | `the output file {file} contains:` | Check a produced file by logical name. |
| `C.LIB.RESULT` | then | lib | `the result is:` | Check the return value (exact or subset) or the logical error raised. |
| `C.QUERY.COUNT` | then | data | `{operation} ran at most {count:int} queries` | Check how many database statements the last action ran, through a counter the project installs on its data access. A list of several records that needs one query per record is the classic N+1 failure; the scenario must seed enough records for it to show. |

`{name:enum(a,b)}` means the placeholder must be one of the listed words. Where a pattern ends in a colon,
a data table (or docstring) follows. Some instructions also have translations (for example Traditional Chinese);
a feature file declares its language with the usual `# language:` header.

## Example

```gherkin
@R-007.1
Rule: An order whose total is 1000 or more gets 10% off the total

  @EX-007.1.2
  Scenario: Exactly on the threshold
    Given alice is signed in as member
    When alice calls place order with:
      | total   |
      | 1000.00 |
    Then the response contains:
      | total | discount |
      | 900   | 100      |
```

`alice`, `member`, `place order` and the table columns come from the glossary and the system map; everything else is
a core instruction.

## Sharing steps between projects

A platform team can keep the domain steps that several projects use in one file and let each project include it. Put the
file inside the project (a vendored copy or a git submodule) and name it in `.bdd/vocabulary.toml`:

```toml
extends = "core"

[vocabulary]
include = ["vendor/team-vocabulary.toml"]
```

An included file has the same format as the project's own: steps with ids that start `D.`, each composing core
instructions. It may include other files; a cycle is an error that names the chain. A name must be a `.toml` file
relative to the project root and may not resolve outside the project, also through a symbolic link.

| Rule | Why |
|---|---|
| A project step cannot reuse the id of a shared step | the shared meaning must not change silently in one project |
| Two shared files cannot define the same id | one definition per step |
| The same pattern in two files is `L014` | a step that matches both would be ambiguous |
| Near-duplicate patterns across files are `L010`, reported in the file the project owns | as for the project's own steps |

**Pinning.** The shared files decide what scenarios mean, so a change has to be seen. `bdd vocabulary pin` records the hash
of every included file in `.bdd/vocabulary.lock.json` after a person has read them; until then, and whenever a file
changes, is added or is no longer included, `bdd lint` reports `L013`. Pinning is the person's act: the guard refuses `bdd vocabulary pin` (and `bdd init --shared-vocabulary`) in
every tool call, so run it yourself (in Claude Code, type `! bdd vocabulary pin`). Agents cannot write the included files
or the lock, also when the include list is broken or a file is only named in the lock, and the tripwire reports a change
by any route. `bdd vocabulary list` shows where each step is defined and `bdd vocabulary
check` runs the vocabulary checks without the feature files. In an existing project, `bdd init --shared-vocabulary FILE`
adds the include and pins it in one step.

A pin proves that the file is the one a person read. It does not prove that the file is right.
