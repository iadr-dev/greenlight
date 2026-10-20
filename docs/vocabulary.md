# The step vocabulary

greenlight scenarios are written from a fixed, versioned set of **core instructions**. Each is a sentence pattern with
`{placeholders}`; the adapter binds it to a driver, so the same scenario text means the same thing in every project.
`bdd lint` rejects a step that matches no instruction (and any step that describes *how* instead of *what*:
clicks on selectors, SQL, URLs).

A project adds its own phrases in `.bdd/vocabulary.toml`, each composed from the core instructions, never as raw code.
The project glossary (`.bdd/glossary.md`) gives the domain words (entities, actors, roles, operations) that fill the
placeholders.

## Profiles

An adapter declares the profiles it supports; a project uses the instructions of those profiles.

| Profile | For |
|---|---|
| `base` | every project |
| `api` | HTTP/RPC services |
| `ui` | web, mobile and desktop UIs |
| `cli` | command-line tools and scripts |
| `lib` | libraries, SDKs and pure domain modules (shares the file instructions with cli) |

## Core instructions (version 1)

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
