# greenlight's own specs

greenlight specifies its own command-line behaviour the way it asks its users to: Gherkin features with trace tags
(`@FEAT-n`, `@R-n.m`, `@EX-n.m.k`), written in the step vocabulary, run through the `python-pytest-bdd` adapter.
The features contain no paths, flags or exit codes: `tests/drivers/operations.py` maps names such as `lint` and
`violations found` to the real tool.

```sh
sh tools/bdd/bdd lint specs/features          # the specs obey the rules the plugin enforces
cd specs && python -m pytest -q               # needs pytest and pytest-bdd (requirements-dev.txt)
```

The detailed behaviour (parsing, hashing, every lint code) is covered by the unit tests in `tools/bdd/tests`; these
specs describe what a person using the tool sees. New CLI behaviour gets its feature here first.
