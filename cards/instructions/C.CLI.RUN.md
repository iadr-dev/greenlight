---
id: C.CLI.RUN
kind: instruction
apply_when: the thing under test is a command-line tool or script
---
## Semantics

Run a logical command (args, env, stdin from the table) in the temporary workspace; capture exit code, stdout and stderr. Binary and flags are mapped in the driver.

Kind: **when**. Profile: cli. Carries: table or docstring optional.

## In practice

Run a command by logical name in the scenario workspace with arguments, environment and standard input given in a table; keep the exit code, standard output and standard error.

## Patterns

- `{actor} runs {command}`
- `{actor} runs {command} with:`

## Good and bad Gherkin

Good:

```gherkin
When alice runs export report with:
  | key | value        |
  | arg | --format csv |
```

Bad:

```gherkin
When alice runs `python -m app export --format csv > out.csv`
```

## Python adapter

`COMMANDS` in `operations.py` maps the name to the program and fixed arguments. Table keys: `arg` (repeat for several), `stdin`, `env.NAME`.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Shell syntax (pipes, redirects) in features. The driver runs the program directly.
- Depending on the machine's environment variables; give the ones that matter in the table.
- A command that prompts for input and waits forever: provide `stdin` or a flag.
