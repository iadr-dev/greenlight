# FAQ

**Does the AI approve its own rules and examples?**
No. Under `guided` and `standard` only you can, by typing `/greenlight:approve FEAT-n rules|examples`. A hook records
what you typed and checks it against the session transcript; a command run by the AI, or typed text quoted in a tool
result, does not count. Under `auto` and `autopilot` the orchestrator records the approvals as *automatic* and the
report says so (autopilot reports are marked UNREVIEWED).

**What stops the AI from editing a test to make it pass?**
Locks. Approving the examples locks the feature files; the bind gate locks steps, drivers and the adapter's plumbing.
The guard blocks writes to locked files, the implementer agent cannot write tests at all, and a tripwire checks the
effect after every tool call, whatever command caused it. A changed locked file blocks the implement and verify gates.

**Is it a sandbox?**
No. greenlight makes tampering visible and blocks the common routes; it cannot stop someone who can run arbitrary code
as you. Production code runs inside the test process, so code written to detect and game the run is possible in
principle; the auditor reads the diff for that. For guarantees that hold even then, add the deny rules `bdd doctor`
shows to `.claude/settings.json` (only you can add them) and run the gates in CI.

**Hard or soft enforcement: which am I in?**
`/greenlight:status` and the report say. Hard needs the hooks to be active. If hooks cannot run (for example Git for
Windows is not installed) greenlight works in soft mode: violations are detected afterwards, not prevented. You can pin
`enforcement = "hard"` in `.bdd/config.toml` to refuse self-reported approvals.

**Can I use it from Codex or another agent tool?**
Yes, in soft mode. `bdd install-skills codex` installs the skills for Codex and `bdd install-skills agents-md` adds a
block to `AGENTS.md` for tools that read it; `bdd install-skills claude` does the same for Claude Code without the
plugin. `--uninstall` removes exactly what was installed. Those tools run no greenlight hooks, so nothing is prevented, only
detected afterwards: run `bdd lock FEAT-n --check --require` in CI. See [concepts](concepts.md).

**Which languages and test stacks are supported?**
Today: Python with pytest and pytest-bdd, Go with godog, .NET with Reqnroll (services, libraries, command-line tools), web UIs
with Playwright (TypeScript), and any other runner that writes a JUnit report through the generic-junit adapter. See
[adapters](adapters.md). The `bdd` tool itself is language independent and needs only Python 3.11+ on the machine.

**Do I have to write Gherkin?**
No; the qa-designer does, from the approved rules, in a fixed [vocabulary](vocabulary.md). You review it.

**Can CI check that the approvals are real?**
Partly. `bdd approve FEAT-n --check` judges the committed record alone, with no session: the approved files must still
match the hashes recorded at approval, the recorded origin must be one the project accepts (a person's typed prompt that was
verified against the transcript, or an automatic or self-reported approval where the autonomy level and enforcement allow
it), and every approval a later phase rests on must exist. It cannot re-read the session transcript, which stays on the
machine where the person typed, and it cannot tell a hand-edited `state.json` from a genuine one, because the record is not
signed; protect the branch (required reviews, no direct pushes) for that. See [CI](ci.md).

**Can production code cheat the tests?**
It runs inside the test process, so it could in principle detect that tests are running. The auditor reads the diff for
that, and the optional mutation check (`bdd mutate`) adds a second line: code that only satisfies the tests tends to
leave surviving mutants. The Python adapter ships a wrapper for mutmut and the Playwright adapter one for Stryker, so
turning the check on is an install and a few lines of configuration. See [adapters](adapters.md).

**Does greenlight enforce a language standard, a style, or "the latest version, nothing deprecated"?**
It enforces what the project declares. `.bdd/standards.md` (written and approved by you) states the language and
toolchain version, style, quality rules and deprecation policy; `[adapters.quality.NAME]` tables name your own formatter,
linter, type checker and deprecation check, which `bdd check` runs and the gates require. A new project should start on
the current stable release; an existing one keeps its version until you decide to upgrade, and no agent upgrades or adds a
toolchain or dependency on its own. See [concepts](concepts.md) and the language cards under `cards/practices`.

**Does greenlight consider APIs and databases: schema design, N+1 queries, migrations?**
Yes, as far as a test or a check can show it. The standards file has API and data sections; the system map copies the contract from your schema file and draws the tables in the design view; a scenario can limit the queries an action runs (`{operation} ran at most {count:int} queries`, seed three or more records so a query per record shows); your own contract, breaking-change and migration tools run as `[adapters.quality.NAME]` checks; and the auditor judges the contract, migrations, schema and query counts. It does not measure speed at production volume, and load testing is outside its scope. See [concepts](concepts.md).

**Can I add my own step phrases?**
Yes, in `.bdd/vocabulary.toml`; each one must be composed from core instructions so it still means something the
drivers can execute.

**Can one feature span several repositories?**
Yes: name the other repositories in a `[workspace]` table in the home repository's `.bdd/config.toml`. The home keeps the
rules, approvals and report; each member keeps its own scenarios, locks and recorded runs under the same ids, and the home's
gates read them. See [concepts](concepts.md).

**Can I use it on an existing code base?**
Yes. New features and changes work as on any project; scenarios that describe behaviour the system already has are
tagged `@existing` so they may pass before implementation. To bring existing code under greenlight, run
`/greenlight:adopt "<module, API area or command>"`, one bounded area at a time: it writes rules and examples that say
what the code does today (you approve them), tests that pass from the start, and locks, without changing any production
code. Afterwards a change to that area goes through `/greenlight:feature` with a safety net behind it.

**What does it cost?**
A feature runs several agents; a small feature with Sonnet-class models is a modest number of turns, a large one is
not. `bdd cost` records what each phase used and the report shows it. The autonomy level and `--quick` control how much
ceremony you pay for.

**How do I stop or undo a feature?**
Nothing is applied outside your working tree: the feature is files under `.bdd/` plus tests and code in git. Use git to
revert. To change approved work while keeping the history, use `/greenlight:change`.

**Why Python in a tool for any language?**
It is installed nearly everywhere, the standard library is enough (TOML, JSON, XML), and one deterministic
implementation of the checks is easier to trust than prompts that re-derive them.
