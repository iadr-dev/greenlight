"""`bdd vocabulary`: the project's domain steps and the shared vocabularies it includes.

    bdd vocabulary list [--json]     the core instructions by count and every project or shared step with its file
    bdd vocabulary check             the lint checks on those steps, plus whether the shared files are what was pinned
    bdd vocabulary pin               record the hashes of the included files, after a person has read them

Pinning is the person's act: the files it covers are read-only for agents, the lock is guarded, and the tripwire
reports a change to either. See ``sharedvocab`` for the file format.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config as cfg
from . import lint, sharedvocab, vocabulary
from .errors import UsageError
from .issues import ERROR
from .statecmd import guarded, project_root


def load(root):
    config = cfg.load(root)
    path = config.vocabulary_file
    if path is None or not path.is_file():
        raise UsageError("this project has no .bdd/vocabulary.toml")
    return config, path, vocabulary.load(path)


def listing(root, as_json: bool) -> None:
    _, path, vocab = load(root)
    shared = sharedvocab.closure(root, path)
    rows = [{"id": e.id, "kind": e.kind, "file": sharedvocab.relative(root, Path(e.origin)),
             "patterns": [p.text for p in e.patterns.get("*", ())], "owner": e.owner}
            for e in vocab.entries if e.source == "project"]
    core = sum(e.source == "core" for e in vocab.entries)
    if as_json:
        print(json.dumps({"core": core, "included": [sharedvocab.relative(root, f) for f in shared], "steps": rows},
                         indent=2, ensure_ascii=False))
        return
    print(f"{core} core instruction(s); {len(rows)} project or shared step(s); {len(shared)} included file(s)")
    for row in rows:
        print(f"  {row['id']:<28} {row['kind']:<5} {row['file']}" + (f"  (owner: {row['owner']})" if row["owner"] else ""))


def check(root) -> int:
    config, path, vocab = load(root)
    issues = lint.check_project_vocabulary(vocab, path, config, config.profiles)
    for issue in issues:
        print(issue)
    errors = sum(i.severity == ERROR for i in issues)
    print(f"vocabulary: {errors} error(s), {len(issues) - errors} warning(s)")
    return 1 if errors else 0


def pin(root) -> None:
    _, path, _ = load(root)                              # refuses cycles, overrides and unreadable files
    pinned = sharedvocab.pin(root, sharedvocab.closure(root, path))
    if not pinned:
        print("no shared vocabulary is included; nothing is pinned")
        return
    print(f"pinned {len(pinned)} shared vocabulary file(s):")
    for name, digest in sorted(pinned.items()):
        print(f"  {digest[:12]}  {name}")


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd vocabulary", description="Project and shared domain steps.")
    sub = ap.add_subparsers(dest="action", required=True)
    show = sub.add_parser("list", help="the project and shared steps and where each is defined")
    show.add_argument("--json", action="store_true")
    sub.add_parser("check", help="lint the project and shared steps and compare the shared files with their pins")
    sub.add_parser("pin", help="record the hashes of the included files as approved")
    args = ap.parse_args(argv)

    def action() -> int:
        root = project_root().resolve()
        try:
            if args.action == "check":
                return check(root)
            {"list": lambda: listing(root, args.json), "pin": lambda: pin(root)}[args.action]()
            return 0
        except (vocabulary.VocabularyError, sharedvocab.IncludeError, cfg.ConfigError) as exc:
            raise UsageError(str(exc)) from exc

    return guarded("vocabulary", action)
