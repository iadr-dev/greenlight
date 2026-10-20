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
block to `AGENTS.md` for tools that read it. Those tools run no greenlight hooks, so nothing is prevented, only
detected afterwards: run `bdd lock FEAT-n --check --require` in CI. See [concepts](concepts.md).

**Which languages and test stacks are supported?**
Today: Python with pytest and pytest-bdd (services, libraries, command-line tools) and web UIs with Playwright
(TypeScript). See [adapters](adapters.md) for what is planned. The `bdd` tool itself is language independent and needs only Python 3.11+ on the machine.

**Do I have to write Gherkin?**
No; the qa-designer does, from the approved rules, in a fixed [vocabulary](vocabulary.md). You review it.

**Can production code cheat the tests?**
It runs inside the test process, so it could in principle detect that tests are running. The auditor reads the diff for
that, and the optional mutation check (`bdd mutate`) adds a second line: code that only satisfies the tests tends to
leave surviving mutants. See [adapters](adapters.md).

**Can I add my own step phrases?**
Yes, in `.bdd/vocabulary.toml`; each one must be composed from core instructions so it still means something the
drivers can execute.

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
