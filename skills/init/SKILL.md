---
name: init
description: Set this repository up for greenlight - check the machine, pick and apply a test adapter, and prove the sample feature runs green. Use when the user runs /greenlight:init or asks to set up or diagnose greenlight.
---

# greenlight init

Prepare a repository for spec-driven development. Do the steps in order and show command output unchanged.
Do not change anything on the machine without asking first.

1. **Check the machine.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" doctor
   ```

   For every `WARN` or `FAIL` line, repeat its `fix:` text and offer to help. If the command cannot run (exit
   code 127) the machine has no Python 3.11 or newer: relay the message the wrapper printed and stop.
   The `deny rules` line (once the project exists) has a JSON snippet that only the person can add to
   `.claude/settings.json`; show it, explain that Claude Code applies deny rules before any hook so they hold
   even when a shell command is spelled in a way the guard cannot read, and do not try to write the file.

2. **Find the adapter.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" init --detect
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" adapter list
   ```

   Recommend one adapter from what was detected and say why. If nothing fits, say so plainly: only the adapters
   listed exist today. Detection suggests the dedicated adapters: `go-godog` for a Go module (`go.mod`), `ts-cucumber-js` for a Node or TypeScript service or tool (`package.json`), `dart-flutter-test` for a Flutter app (`pubspec.yaml`), `dotnet-reqnroll` for a .NET project
   (`*.csproj`, `*.sln`), `java-cucumber-spring` and `kotlin-android` for the JVM. If the project's test runner can write a JUnit XML report and none of them fits, offer `generic-junit` (it is never
   suggested by detection) and tell the person they will replace its sample run command with their runner's. Ask the person to confirm the adapter and the starting autonomy level
   (`guided` reviews every gate, `standard` asks only for rules and examples; `auto` and `autopilot` are for
   trusted or hands-off work). Wait for the answer.

3. **Set the repository up and record what the project already has.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" init --adapter NAME --autonomy LEVEL
   ```

   It creates `.bdd/` (configuration, glossary, an ignore file for machine-local data) and copies the adapter's
   files into the project without overwriting anything. List what it created.

   It then reads the project's own files and records what they show, and prints one line for each record. Show these
   lines unchanged and say in plain words what each one means for the person:

   - `sources:` and `frameworks:` are the services and frameworks the dependency files name, recorded with their official
     documentation, vendor command-line tool and plugin in `.bdd/sources.toml`. The writers read that documentation
     instead of guessing. A package that is not in greenlight's catalog is not guessed at; the person can add an entry.
   - `vendor tools:` says whether each vendor CLI is on this machine. Never install one. If it is missing, say what it is for
     and leave it to the person.
   - `quality:` are the formatter, linter, type checker and architecture checker the project itself declares, now written
     as `[adapters.quality.NAME]` checks that `bdd check` runs and that the implement and verify gates ask for. They are in
     force from now on. Say which ones, say that the person can edit or delete them in `.bdd/config.toml`, and do not
     ask for approval of the commands. A tool the project does not declare is never added.
   - `design:` is the `design/` folder that was found (DESIGN.md, screens, inventory), recorded as `[design]` for the design
     and design-review stages. Nothing in it is read yet.
   - `surfaces:` are the web, iOS, Android, API and command-line surfaces the project ships and the adapter that verifies
     each. For each `unverified` surface say plainly that greenlight will build and test the logic behind it but cannot
     check its screens, and name the adapter the line offers (for web, `ts-playwright-bdd`). Do not add an adapter without
     the person's yes.

   A line that says `none` is a fact, not an error. Run `"${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" init --refresh` later,
   when the project gains a dependency, a design folder or an adapter: it adds what is new and never rewrites what the
   person wrote.

4. **Install the adapter's requirements** if its guide says so (for `python-pytest-bdd`: `pytest` and
   `pytest-bdd`). Show the command and ask before running it; prefer the project's own tool (`uv`, `pip`,
   `poetry`).

5. **Offer the helper plugins, once.** greenlight works without them; they make its roles better (design guidance,
   current library documentation, browser checks, review tools).

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" helpers --json
   ```

   Skip this step when `declined` is true, when `claude_found` is false (say that the plugin list could not be read), or
   when `install` is null (everything recommended is installed: say so in one line). Otherwise show the recommended
   helpers that are missing (name, what it adds, what it needs) and ask once, with a question that has three answers:
   *install them*, *not now*, *do not ask again*.

   - *Install them*: you cannot install plugins. Installing changes the person's Claude Code settings, so the guard refuses
     it from a tool call. Give the person the `install` line from the JSON, exactly as it is, and tell them to type it
     themselves (the leading `!` runs it in their own shell, between prompts). Then go on; do not wait for it, and do not
     try to run it.
   - *Not now*: go on. Nothing is recorded, so the question comes again at the next `/greenlight:init`.
   - *Do not ask again*: run `"${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" helpers --decline`.

   Two more kinds of line can follow, and each is only a suggestion. `vendor` in the JSON lists the plugins of the services in
   `.bdd/sources.toml` (Supabase, Stripe, Expo, Sentry, Cloudflare, AWS, Firebase and the like); show those with `installed`
   false and give the person the `! claude plugin install ...` line from `bdd helpers`, as it is. The optional helpers
   `impeccable`, `pstack` and `open-code-review` come from their authors' own marketplaces, not Anthropic's: name that
   marketplace (the `marketplace` field) before offering one, and give the line `bdd helpers` prints for it. Never run
   either line.

   Never describe a missing helper as required. A project without any of them is fine.

6. **Prove it works.**

   ```sh
   "${CLAUDE_PLUGIN_ROOT}/tools/bdd/bdd" init --smoke
   ```

   It runs the sample feature and cleans up after itself. If it fails, show the output and the likely cause
   (missing requirements, wrong interpreter); do not go on until it is green.

7. **Say what comes next**: start a feature with `/greenlight:feature "<what you want>"`, see where things stand
   with `/greenlight:status`. Mention that approvals of rules and examples are typed by the person as
   `/greenlight:approve FEAT-n rules` and `/greenlight:approve FEAT-n examples`, and that the AI cannot give them.
