---
id: language-python
kind: practice
apply_when: writing or judging production code in a Python project
output: code that follows the project's declared Python version and standards, passes format lint and type checks, and uses no deprecated API
phase: implement
pairs_with: [mutation-check]
---
## Intent

The project's declared toolchain is the standard. The Python version in `pyproject.toml` (`requires-python`) or
`.python-version` decides what is allowed; a new project starts on the current stable release, an existing one stays
where it is until the person decides otherwise. Write for that version, with its current APIs, and let the project's
own tools say whether the code is clean.

## How to apply

1. Read `.bdd/standards.md` and the project's tool configuration (`pyproject.toml`, `ruff.toml`, `mypy.ini`). The
   configuration wins over habit.
2. Commands (use the project's own environment, for example `uv run`):
   - format: `ruff format --check .`
   - lint: `ruff check .` (include the `UP` rules, which flag outdated syntax and deprecated names)
   - types: `mypy .` or `pyright`, in the strictness the project declares
   - deprecations as errors: run the tests with `-W error::DeprecationWarning -W error::PendingDeprecationWarning`, or set
     `filterwarnings = ["error::DeprecationWarning"]` in the bound `tests/pytest.ini`
3. To have greenlight run them, add tables to `.bdd/config.toml` (the file is yours; agents cannot edit it):

   ```toml
   [adapters.quality.format]
   command = '{project_python} -m ruff format --check {root}'

   [adapters.quality.lint]
   command = '{project_python} -m ruff check {root}'

   [adapters.quality.typecheck]
   command = '{project_python} -m mypy {root}'
   ```

4. Read the current documentation of every library you call (the project's docs, or a documentation tool such as
   context7). Do not recall an API from memory.
5. Fix a warning, never silence it. A suppression (`# noqa`, `# type: ignore`) needs a reason on the same line.

## Known pitfalls

- `datetime.utcnow()` and `utcfromtimestamp()` are deprecated since 3.12; use timezone-aware `datetime.now(UTC)`.
- `typing.List`, `Dict`, `Optional[X]` where the declared version allows `list`, `dict`, `X | None`.
- `asyncio.get_event_loop()` outside a running loop, `pkg_resources`, `distutils`, `imp`: removed or deprecated.
- Mutable default arguments, bare `except:`, and `except Exception: pass` hide defects.
- Installing a package to make an import work. Packages are the person's decision; return the missing requirement.
- Running tools with the wrong interpreter. Use the project's own environment, as `bdd run` does.
