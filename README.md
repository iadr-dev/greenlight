<p align="center">
  <img src="docs/assets/logo.svg" width="128" height="128" alt="greenlight logo: a traffic light with the green lamp lit and a check mark">
</p>

<h1 align="center">greenlight</h1>

<p align="center">
  <b>AI × BDD spec-driven development for Claude Code</b><br>
  You approve the contract. The AI does the rest.
</p>

<p align="center">
  <a href="docs/quickstart.md">Quickstart</a> ·
  <a href="docs/concepts.md">Concepts</a> ·
  <a href="docs/adapters.md">Adapters</a> ·
  <a href="docs/faq.md">FAQ</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

greenlight turns a feature request into human-approved,
executable specifications, and then into working code. People approve the contract (rules and examples); the AI does
the mechanical work in between, under gates it cannot talk its way past (with the plugin's hooks; without them, in
soft mode, a violation is detected after the fact, not prevented).

```text
request ─▶ rules ─▶ test design ─▶ examples ─▶ system map + design ─▶ red tests ─▶ tasks ─▶ green code ─▶ audit report
           you      checked        you         checked                proved       checked  proved        evidence
```

- **You approve the contract.** Rules and examples are approved only by what you type
  (`/greenlight:approve FEAT-n rules`), verified against the session transcript, one gate per message.
  `bdd approve FEAT-n rules --summary` shows what you are about to approve in plain words, and after a change only what
  changed since your last approval. You choose how much you are asked (see *Autonomy levels* below); at `autopilot`
  nothing is asked and the report is marked UNREVIEWED.
- **Tests come first, and red must be real.** A recorded run must fail for the intended reason before any code is
  written; a broken test is not a red. A feature reopened after its code exists proves its new red against the code
  as it was (`bdd run --against-red`), never by hiding the code.
- **Evidence is bound.** Approved specs, steps, drivers and the test runner's own settings are locked (the files every
  feature shares are locked once for the project); the interpreter, environment and recorded runs are checked; a
  tripwire notices tampering whatever command caused it. A tripwire finding stays open until the files are restored or
  you type one line to accept it (`/greenlight:approve integrity #3 <reason>`).
- **Your engineering standards are part of the gate.** `.bdd/standards.md` (language and toolchain, clean code,
  architecture, security, API and data rules, deprecation policy) starts as greenlight's defaults and is in force
  without approval; only you can change it. Once you name your formatter, linter and type checker in
  `[adapters.quality.NAME]` tables in `.bdd/config.toml` (`bdd init` writes none), `bdd check` runs them and the gates
  require a passing result. Optional mutation and stability checks (`bdd mutate`, `bdd stability`) test the tests.
- **Mistakes are caught early, not by the auditor at the end.** `bdd lint` refuses two record tables of one entity with
  different columns. `bdd classify` refuses a red in which a scenario tagged `@existing` fails. The test-design gate asks
  for the edge examples a `boundary-value` rule needs. Where the hooks run, the implement gate refuses a review older
  than the code it read.
- **Nine test stacks.** Python (pytest-bdd), TypeScript web UIs (Playwright), Node and TypeScript services
  (cucumber-js), Go (godog), .NET (Reqnroll), Spring Boot, Kotlin/Android (Cucumber-JVM, also on a device or emulator),
  Flutter and Dart (widget tests), and any runner that writes a JUnit report.
- **Other agent tools too.** `bdd install-skills claude|codex|agents-md` installs the instructions for Claude Code
  without the plugin, for Codex, and for anything that reads `AGENTS.md`, in soft mode (detected, not prevented), with
  the same `bdd` checks; `bdd install-hooks codex` adds best-effort blocking through Codex's own hooks. Work done in
  Codex is never graded hard: CI and branch review are the guarantee.
- **Existing code and several repositories.** `/greenlight:adopt` describes code that already exists without changing
  it; a feature can span repositories (`[workspace]`); teams can share a pinned vocabulary.
- **The right specialist for each task, chosen for you.** In the code stage `bdd route` reads each task's scenarios and
  names who writes it (the `implementer`, or the `ui-engineer` for screens) and who reviews it (a `code-reviewer`
  always, a `ui-reviewer` for screens, a `security-reviewer` for signing in, money or personal data). Nobody is asked;
  the implement gate waits for every review, and the report shows the routing and each verdict. Each agent runs on the
  model its file names; `[models]` in `.bdd/config.toml` changes one (`implementer = "opus"`), and `bdd status` shows
  the model of every agent.
- **Deterministic work is code, not prompts.** Lint, trace, locks, gates and classification are the `bdd` command line
  (Python 3.11+, standard library only).
- **Traceable.** `@FEAT-n`, `@R-n.m` and `@EX-n.m.k` tags tie every rule to its examples, tests and code.

> Status: 1.2. Measured results and the known limits are in the [CHANGELOG](CHANGELOG.md); the evaluation harness is
> described in [evals/README.md](evals/README.md).

## See it work

Two short videos, made from one real run of greenlight on its demo shop app (`evals/apps/shop-api`, the request
"Give big orders a discount"). The rules, scenarios, failures and report on screen are that run's own records.

<table>
<tr>
<td width="50%" valign="top">

**1 · Set up and ask for a feature** · 28 s

Install the plugin, run `/greenlight:init`, and ask for a feature. The phases are drawn, and two of them are yours to approve.

https://github.com/user-attachments/assets/098018a6-49bc-4d83-8cff-00001503e350

</td>
<td width="50%" valign="top">

**2 · Approve, prove, ship** · 40 s

Read the rules and examples, approve and lock them, watch every example fail and then pass, and read the report.

https://github.com/user-attachments/assets/1e2f0245-adcb-4051-b947-e193cdf63dbe

</td>
</tr>
</table>

In the videos the approval step is re-enacted (the sample run used automatic approvals), and the run stops before the
independent audit, so the report shows what was recorded up to the green run.

## How it works

1. **Set up once.** `/greenlight:init` checks the machine, recommends a test adapter for you to confirm, creates
   `.bdd/` and the adapter's `tests/` skeleton, and proves a sample feature runs (install the adapter's test
   requirements first; for Python, `pytest` and `pytest-bdd`). It writes greenlight's default engineering standards to
   `.bdd/standards.md`; they apply at once, and you may edit them.
2. **Ask for a feature.** `/greenlight:feature "what you want"` runs the phases: discover, specify (rules), test design,
   examples (Gherkin scenarios), system map (which also writes the design view, `design.md`), refine, bind, tasks,
   implement and verify. `/greenlight:feature "..." --quick` takes the short path for a change of one rule
   (`phases/quick.md`).
3. **Approve the contract.** You read `rules.md` and the scenarios and approve each by typing
   `/greenlight:approve FEAT-n rules|examples`. Approved examples lock the feature files.
4. **Red, then green.** The steps and drivers are written and run; every new scenario must fail for the intended
   reason before any code is written. Then each task goes to the writer `bdd route` picks for it, which writes the code
   until its scenarios pass, and to its reviewers (code, UI, security), whose must-fix findings go back to the writer.
5. **Verify.** The `spec-auditor` agent is read-only. It checks the evidence against `review/checklist.md` and returns
   a report, which the orchestrator saves as `report.md`. `Verdict: PASS` means no blocking checklist item failed. That
   covers more than the rules and the tests. It includes approvals given the way the mode requires, a red proven before
   any code, every review done and current, the engineering standards met, and shuffled and isolated runs green.
6. **Hand over.** `bdd check FEAT-n` runs your formatter, linter and type checker, once you have named them;
   `bdd pr FEAT-n --write` writes `PULL_REQUEST.md` from the recorded facts. CI re-checks locks, approvals and
   traceability when you copy the adapter's `ci/github-actions.yml` to `.github/workflows/` (see [CI](docs/ci.md)).
7. **Change later** with `/greenlight:change`, which reopens at the earliest phase the change touches.

### Who does the work

| Phase | Agent |
|---|---|
| discover, specify | `product-analyst` |
| test design, examples | `qa-designer` |
| system map | `system-analyst` |
| refine, bind | `step-engineer` |
| tasks | the orchestrator |
| implement | `implementer`, or `ui-engineer` for screens; reviewed by `code-reviewer`, `ui-reviewer`, `security-reviewer` |
| verify | `spec-auditor` |

The orchestrator (`/greenlight:feature`) runs the phases, records every result and starts the agents. They read files,
not chat history, and each writes only the files of its role.

### Autonomy levels

| Level | Asks you |
|---|---|
| `guided` | at every human gate, after test design, and shows the design view before binding |
| `standard` | for the rules and the examples |
| `auto` | the two approvals are recorded automatically; blocking questions still come to you |
| `autopilot` | nothing; assumptions are recorded and the report is marked UNREVIEWED |

Machine gates are never skipped at any level. Start with `guided`. To hand the rest of a feature to the AI while it
runs, say "you decide" in the conversation. The orchestrator switches to `autopilot` and records your words, using
`bdd mode FEAT-n --switch autopilot --reason "..."`. Approvals already given stay yours.

## Install

```text
/plugin marketplace add iadr-dev/greenlight
/plugin install greenlight@greenlight
```

Requires Python 3.11+ (standard library only) and a POSIX `sh`: native on Linux and macOS, Git for Windows on Windows.
With Git for Windows installed, hooks run in Git Bash whether you start `claude` from PowerShell or from Git Bash (both
were tested; a `cmd.exe` launch was not). The plugin's hooks and its skills call the `sh` wrapper
`tools/bdd/bdd`. Without Git for Windows the hooks cannot run, so nothing is prevented (soft at most), and whether the
skills' `bdd` calls work without `sh` was not tested: install Git for Windows. For a check by hand on a machine without
`sh`, the CLI also runs as `python -I <plugin folder>/tools/bdd/main.py <command>`.

Each adapter also needs its own stack on the machine, which greenlight never installs for you: `pytest` 8+ and
`pytest-bdd` 8+ for Python; Node.js and pnpm for the TypeScript adapters (web UI and Node services; CI uses Node 26);
Go 1.24 or newer (CI uses 1.27); the Flutter SDK for the Flutter adapter; the .NET 10 SDK; a JDK with Maven or Gradle for
Spring Boot and Kotlin/Android (CI uses JDK 25). `/greenlight:init` checks your machine.

greenlight writes `.bdd/` (commit it; its machine-local `.enforcement/`, `.integrity/` and `.runs/` folders are
ignored) and the adapter's `tests/` skeleton into your repository, and never overwrites an existing file. To remove it,
delete those folders and any deny rules you added to `.claude/settings.json`. `bdd install-skills ... --uninstall`
removes the skills it installed outside the plugin, and `bdd install-hooks codex --uninstall` removes the hook entries it
added to Codex.

### First run

`/greenlight:init` runs `bdd doctor` first. Before `.bdd/` exists, doctor checks only the machine (Python, `sh`, git,
hook speed, helper plugins). The project checks below appear once init has created `.bdd/`, so run `bdd doctor` again
afterwards, or `/greenlight:init` again. Some of these warnings are normal before the first session:

- `enforcement: no hook has run in this project yet, so nothing is prevented (soft)` goes away after the plugin's guard
  hook has run once here, which it does at the first edit or shell command of a Claude Code session in the project.
- `integrity: no baseline yet` goes away at the next prompt, which takes the baseline.
- `deny rules: ... recommended deny rules are not set` stays until you add them. Only you can, because the agent may not
  edit `.claude/settings.json`. Copy the JSON that doctor prints into `.claude/settings.json` of the project (committed,
  so the team shares it) or into your user settings, merging it into any `permissions.deny` list already there.
- `codex hooks` appears only where the `codex` program is installed. See [concepts](docs/concepts.md#enforcement-in-codex).

Anything else is explained in [troubleshooting](docs/troubleshooting.md).
<!-- P2 FILLS THIS: the typed line that adds the deny rules (bdd doctor --add-deny-rules) goes after the deny rules item above. -->

### Running `bdd` yourself

Skills and hooks run `bdd` for you; you can also ask Claude to run a command. To run it from your own terminal, `bdd` is
not on your `PATH`. Call the wrapper in the plugin folder, which is the `installPath` of `greenlight@greenlight` in
`claude plugin list --json` (under `~/.claude/plugins/cache/greenlight/greenlight/<version>/` by default):

```sh
sh "<plugin folder>/tools/bdd/bdd" status
```

Every `bdd ...` line in these docs means that command. Feature ids are zero-padded, `FEAT-001`;
`bdd state next-id` prints the next free one.

### Plugins greenlight can use

greenlight works on its own: its roles carry their knowledge in `cards/` (UI design, accessibility, security, API
design, databases, each language) and use the project's own tools. `/greenlight:init` offers the seven recommended
plugins below once (`bdd helpers` lists them any time, with the line that installs the missing ones); nothing is
installed unless you type that line yourself, and "do not ask again" is remembered. When a plugin below is installed, the
roles use it too, always in a mode that reports and never in one that edits code or tests.

Offered by `bdd helpers` (the id is what `claude plugin list` shows):

| Plugin id | Used by | For |
|---|---|---|
| `frontend-design@claude-plugins-official` | ui-engineer | the design plan of a new screen |
| `context7@claude-plugins-official`, `microsoft-docs@claude-plugins-official` | the writers (implementer, ui-engineer) | the current official documentation of a library |
| `chrome-devtools-mcp@claude-plugins-official` | ui-reviewer | accessibility and visual checks in a browser, when the app can be started |
| `code-metrics-complexity-and-duplication-report@anthropic-plugin-directory` (`bdd helpers` calls it `code-metrics`) | code-reviewer | complexity and duplication of the changed files |
| `api-drift-detector-typescript-contract-checker@anthropic-plugin-directory` | code-reviewer | drift between API types, schemas and the database |
| `feature-dev@claude-plugins-official` | code-reviewer | a read-only review checklist |
| `figma@claude-plugins-official` (listed as optional, left out of the install line) | ui-engineer | building from a Figma design, when the task names one (needs your Figma login) |

Used when you have installed them yourself, which greenlight never offers: `impeccable@impeccable` (ui-reviewer: its
`audit` and its finish reviewer's criteria, not the modes that edit code or ask you), `pstack@pstack-claude` (code-reviewer:
its `thermos` and `interrogate` skills) and `open-code-review@open-code-review` (code-reviewer: the `ocr` command in
report-only mode).

Not used inside the pipeline, because their own flows write tests or record approvals: `superpowers` (its TDD and
subagent-driven development) and `pstack`'s `poteto-mode` and `tdd`. Their hooks still run if you have them installed;
greenlight's guard keeps every agent away from the tests whatever a hook suggests.

## Use

The six slash commands, typed in Claude Code:

```text
/greenlight:init                                  # check the machine, recommend an adapter, prove the sample runs
/greenlight:feature "what you want"               # run a feature through the phases
/greenlight:feature "what you want" --quick       # the short path for a change of one rule
/greenlight:approve FEAT-001 rules                # you, after reading rules.md
/greenlight:approve FEAT-001 examples             # you, after reading the scenarios
/greenlight:approve integrity #3 <reason>         # you, to accept a tripwire finding that you made on purpose
/greenlight:adopt "orders module"                 # describe code that already exists, change nothing
/greenlight:status                                # where everything stands
/greenlight:change FEAT-001 "what changes, why"   # change approved work, keeping the history
```

The `bdd` command line, which the skills run for you. From a terminal, write `sh "<plugin folder>/tools/bdd/bdd"` where
these lines say `bdd` (see *Running `bdd` yourself*), or ask Claude to run them:

```text
bdd init --detect                                 # which adapter fits this repository, and why
bdd approve FEAT-001 rules --summary              # what you are about to approve, in plain words
bdd route FEAT-001                                # who writes and who reviews each task, and why
bdd check FEAT-001                                # your formatter, linter and type checker, once configured
bdd mode FEAT-001 --switch autopilot --reason "you decide"   # change the autonomy level, with your words
bdd pr FEAT-001                                   # a pull-request description from the recorded facts
bdd report FEAT-001 --out reports/FEAT-001.html   # a readable HTML report of the feature, for non-developers
```

## Known limits

- At `autopilot` nobody reviews the rules or the examples; the report says so. At `standard` a person must approve the
  rules, so an unattended run stops there.
- Without hooks (no Git for Windows, Codex, `AGENTS.md`) enforcement is soft, and work done in Codex is never graded hard.
- The Python mutation check (`bdd mutate`) needs WSL on Windows, because mutmut does not run natively there; nothing else
  does.
- A dependency folder (`node_modules`, `.venv`, `venv`) that holds `next/package.json` is copied, not linked, when
  `bdd run --against-red` re-proves a red, because Turbopack (Next.js 16) does not read `next` through a link. The copy
  costs disk space and time.
- Measured results from end-to-end runs, and what they do not show, are in the [CHANGELOG](CHANGELOG.md).

## Documentation

- [Quickstart](docs/quickstart.md): install to verified feature
- [Concepts](docs/concepts.md): phases, gates, locks, autonomy levels, enforcement
- [Vocabulary](docs/vocabulary.md): the step phrases scenarios are written from
- [Adapters](docs/adapters.md): test stacks, which Python runs the tests, quality and mutation checks
- [CI](docs/ci.md): re-check locks, the green run, approvals and traceability in a pipeline
- [Upgrading](docs/upgrading.md), [FAQ](docs/faq.md), [Troubleshooting](docs/troubleshooting.md)
- [A filled-in example feature](docs/examples/order-discounts)
- For contributors: [CLAUDE.md](CLAUDE.md), [design decisions](docs/dev/decisions.md), [platform notes](docs/dev/platform-notes.md)

## License

MIT
