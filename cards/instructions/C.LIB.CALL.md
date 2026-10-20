---
id: C.LIB.CALL
kind: instruction
apply_when: the unit of behaviour is a public function or method of a library or domain module
---
## Semantics

Invoke a public function or method by logical name; capture the return value or the raised error.

Kind: **when**. Profile: lib. Carries: table or docstring.

## In practice

Call a public function by logical name and keep its return value or the error it raised, for the Then steps to judge.

## Patterns

- `{operation} is called with:`

## Good and bad Gherkin

Good:

```gherkin
When add is called with:
  | a | b |
  | 2 | 3 |
```

Bad:

```gherkin
When the private helper _round_half_even is called
```

## Python adapter

`LIB` in `operations.py` maps the name to `module:function`. A table row becomes keyword arguments; a list doc string becomes positional arguments. Exceptions are captured, not raised.

These notes describe the `python-pytest-bdd` adapter; other adapters implement the same instruction with their own drivers.

## Known pitfalls

- Calling private functions: the example then pins the implementation, not the behaviour.
- Arguments that are Python objects. Pass data; build objects in the driver.
- Expecting the driver to catch everything: a missing function is a failure, not a captured error.
