"""`bdd lint`: check feature files against the step vocabulary.

Every finding has a stable code so reports can refer to it:

    L001 error    file does not parse as Gherkin
    L002 error    step matches no vocabulary entry (no suggestion is guessed silently)
    L003 error    step matches more than one vocabulary entry
    L007 error    step uses a core instruction from a profile the project has not enabled
    L008 error    table / doc string does not fit what the instruction accepts
    L009 error    Scenario Outline parameter mismatch (warning for unused Examples columns)
    L011 warning  step is marked ``# proposed-step`` and still has to be added to the vocabulary
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from . import config as cfg
from . import gherkin, vocabulary

ERROR, WARNING = "error", "warning"
_OUTLINE_PARAM = re.compile(r"<([^<>]+)>")
_WORD = re.compile(r"[^\W\d_]+|\d+", re.UNICODE)
_PLACEHOLDER = re.compile(r"\{[^{}]*\}|<[^<>]*>")


@dataclass(frozen=True)
class Issue:
    path: str
    line: int
    severity: str
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.severity} {self.code}: {self.message}"


# -- steps -------------------------------------------------------------------------------
def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(_PLACEHOLDER.sub(" ", text))}


def suggest(vocab: vocabulary.Vocabulary, kind: str, text: str, language: str) -> str:
    """Name the closest pattern of the same kind, if any is reasonably similar."""
    mine, best, best_score = _tokens(text), None, 0.0
    for entry in vocab.entries:
        if entry.kind != kind:
            continue
        for pattern in entry.candidates(language):
            theirs = _tokens(pattern.text)
            score = len(mine & theirs) / len(mine | theirs) if mine | theirs else 0.0
            if score > best_score:
                best, best_score = (entry.id, pattern.text), score
    return f" Closest: {best[0]} \"{best[1]}\"." if best and best_score >= 0.4 else ""


def shape_problem(requires: str, step: gherkin.Step) -> str | None:
    has_table, has_doc = step.table is not None, step.docstring is not None
    if requires == "none" and (has_table or has_doc):
        return "this instruction takes no table or doc string"
    if requires == "table" and not has_table:
        return "this instruction needs a data table" + (" (got a doc string)" if has_doc else "")
    if requires == "docstring" and not has_doc:
        return "this instruction needs a doc string" + (" (got a table)" if has_table else "")
    if requires == "table_or_docstring" and not (has_table or has_doc):
        return "this instruction needs a data table or a doc string"
    return None


class Linter:
    def __init__(self, vocab: vocabulary.Vocabulary, profiles: tuple[str, ...] = cfg.ALL_PROFILES):
        self.vocab, self.profiles = vocab, set(profiles)

    def check_step(self, step: gherkin.Step, language: str, path: str) -> list[Issue]:
        matches = self.vocab.resolve(step.kind, step.text, language)
        where = f'{step.keyword} {step.text}'
        if not matches:
            if step.proposed:
                return [Issue(path, step.line, WARNING, "L011", f'proposed step "{where}" is not in the vocabulary yet')]
            hint = suggest(self.vocab, step.kind, step.text, language)
            return [Issue(path, step.line, ERROR, "L002", f'no vocabulary entry matches "{where}".{hint}')]
        if len(matches) > 1:
            ids = ", ".join(m.entry.id for m in matches)
            return [Issue(path, step.line, ERROR, "L003", f'"{where}" is ambiguous: matches {ids}')]
        entry = matches[0].entry
        issues = []
        if entry.source == "core" and not self.profiles.intersection(entry.profiles):
            issues.append(Issue(path, step.line, ERROR, "L007",
                                f"{entry.id} belongs to profile(s) {'/'.join(entry.profiles)}, "
                                f"which this project has not enabled ({', '.join(sorted(self.profiles))})"))
        problem = shape_problem(entry.requires, step)
        if problem:
            issues.append(Issue(path, step.line, ERROR, "L008", f"{entry.id}: {problem}"))
        return issues

    @staticmethod
    def outline_params_used(scenario: gherkin.Scenario) -> dict[str, int]:
        """Every <parameter> a step refers to (in its text, table or doc string) -> first line."""
        used: dict[str, int] = {}
        for step in scenario.steps:
            blobs = [step.text, step.docstring or "", *(cell for row in (step.table or []) for cell in row)]
            for blob in blobs:
                for name in _OUTLINE_PARAM.findall(blob):
                    used.setdefault(name.strip(), step.line)
        return used

    def check_outline(self, scenario: gherkin.Scenario, path: str) -> list[Issue]:
        if not scenario.outline:
            return []
        if not scenario.examples:
            return [Issue(path, scenario.line, ERROR, "L009", f'Scenario Outline "{scenario.name}" has no Examples')]
        used = self.outline_params_used(scenario)
        columns = {col for ex in scenario.examples for col in ex.header}
        issues = [Issue(path, line, ERROR, "L009", f"<{name}> is not a column of any Examples table")
                  for name, line in used.items() if name not in columns]
        issues += [Issue(path, ex.line, WARNING, "L009", f'Examples column "{col}" is never used by a step')
                   for ex in scenario.examples for col in ex.header if col not in used]
        return issues

    def check_feature(self, feature: gherkin.Feature, path: str) -> list[Issue]:
        issues: list[Issue] = []
        backgrounds = [feature.background] + [c.background for c in feature.children if isinstance(c, gherkin.Rule)]
        for bg in filter(None, backgrounds):
            for step in bg.steps:
                issues += self.check_step(step, feature.language, path)
        for scenario, _rule in feature.scenarios():
            for step in scenario.steps:
                issues += self.check_step(step, feature.language, path)
            issues += self.check_outline(scenario, path)
        return issues

    def lint_text(self, text: str, path: str = "<string>") -> list[Issue]:
        try:
            feature = gherkin.parse(text, path)
        except gherkin.ParseError as exc:
            return [Issue(path, exc.line, ERROR, "L001", exc.message)]
        return sorted(self.check_feature(feature, path), key=lambda i: (i.line, i.code))

    def lint_file(self, path: Path) -> list[Issue]:
        return self.lint_text(path.read_text(encoding="utf-8-sig"), str(path))


# -- files and CLI -----------------------------------------------------------------------
class UsageError(ValueError):
    """The command line asked for something lint refuses to do."""


def collect_files(paths: list[Path]) -> list[Path]:
    """Expand directories to their .feature files. An explicit file must itself be a .feature:
    lint is called by tools and agents, and parse errors quote the text they stumble on, so it
    must not be usable to read arbitrary files."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.rglob("*.feature")
                            if not any(part.startswith(".") or part == "node_modules" for part in f.relative_to(p).parts))
        elif p.is_file() and p.suffix == ".feature":
            files.append(p)
        elif p.is_file():
            raise UsageError(f"{p} is not a .feature file")
        else:
            raise FileNotFoundError(str(p))
    return files


def vocabulary_file(arg: Path | None, config: cfg.Config) -> Path | None:
    """--vocabulary must be a .toml file inside the project (or the working directory)."""
    if arg is None:
        return config.vocabulary_file
    base = (config.root or Path.cwd()).resolve()
    resolved = arg.resolve()
    if resolved.suffix != ".toml" or not resolved.is_relative_to(base):
        raise UsageError(f"--vocabulary must be a .toml file inside {base}")
    return resolved


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="bdd lint", description="Check .feature files against the step vocabulary.")
    ap.add_argument("paths", nargs="*", type=Path, help="files or directories (default: the project's feature directories)")
    ap.add_argument("--vocabulary", type=Path, help="project vocabulary.toml (default: .bdd/vocabulary.toml)")
    ap.add_argument("--profiles", help="comma-separated profiles to allow (default: from .bdd/config.toml)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    return ap


def prepare(args: argparse.Namespace) -> tuple[Linter, list[Path]]:
    """Resolve configuration, vocabulary and target files; raise UsageError for bad requests."""
    config = cfg.load(cfg.find_root())
    profiles = tuple(args.profiles.split(",")) if args.profiles else config.profiles
    bad = [p for p in profiles if p not in cfg.ALL_PROFILES]
    if bad:
        raise UsageError(f"unknown profile(s): {', '.join(bad)}")
    vocab = vocabulary.load(vocabulary_file(args.vocabulary, config))
    targets = args.paths or list(config.feature_dirs)
    if not targets:
        raise UsageError("no paths given and no feature directories configured")
    return Linter(vocab, profiles), collect_files(targets)


def report(issues: list[Issue], file_count: int, as_json: bool) -> None:
    errors = sum(i.severity == ERROR for i in issues)
    warnings = len(issues) - errors
    if as_json:
        summary = {"files": file_count, "errors": errors, "warnings": warnings}
        print(json.dumps({"summary": summary, "issues": [asdict(i) for i in issues]}, ensure_ascii=False, indent=2))
        return
    for issue in issues:
        print(issue)
    print(f"{file_count} file(s), {errors} error(s), {warnings} warning(s)")


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    try:
        linter, files = prepare(args)
    except (cfg.ConfigError, vocabulary.VocabularyError, FileNotFoundError, UsageError) as exc:
        print(f"bdd lint: {exc}", file=sys.stderr)
        return 2
    issues = [issue for f in files for issue in linter.lint_file(f)]
    report(issues, len(files), args.json)
    return 1 if any(i.severity == ERROR for i in issues) else 0
