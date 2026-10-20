---
id: C.FILE.VERIFY
kind: instruction
apply_when: checking a file that a command or function produced
---
## Semantics

Check a produced file by logical name.

Kind: **then**. Profile: cli, lib. Carries: table or docstring.

## In practice

Check the output file by logical name; the real path is in the file map.

## Patterns

- `the output file {file} contains:`

## Good and bad Gherkin

Good:

```gherkin
Then the output file report contains:
  """
  id,total
  1,1000
  """
```

Bad:

```gherkin
Then the file out/report.csv has 2 lines
```

## Python adapter

`world.workspace.assert_contains(name, text)`; fails clearly when the file was never produced.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Checking the file's existence only.
- Byte-exact comparison of text that differs by line endings.
- Reading files outside the workspace.
