---
id: C.FILE.GIVEN
kind: instruction
apply_when: a command or library reads an input file
---
## Semantics

Create an input file in an isolated temporary workspace. {file} is a logical name; the real path is mapped in the system map.

Kind: **given**. Profile: cli, lib. Carries: table or docstring.

## In practice

Create the file in the scenario's isolated workspace under a logical name; the real path comes from the file map in the driver.

## Patterns

- `the input file {file} contains:`

## Good and bad Gherkin

Good:

```gherkin
Given the input file orders contains:
  """
  id,total
  1,1000
  """
```

Bad:

```gherkin
Given the file /home/me/data/orders.csv exists
```

## Python adapter

`world.workspace.write(name, text)`; `name` must be in `FILES` in `tests/drivers/operations.py`. A table is written as comma-separated lines.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Real paths or files outside the workspace, which break on another machine.
- Line endings: write LF and compare with normalised text.
- Large inputs inline. Keep the example small and put bulk data in a fixture file.
