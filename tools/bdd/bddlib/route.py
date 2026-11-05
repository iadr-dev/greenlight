"""Which roles a task needs: the writer, the reviewers and the cards, read from the task's scenarios.

    bdd route FEAT-n [--json]

The orchestrator does not ask the person who should write or review a task: this command decides, from files the
feature already has, so the same feature is always routed the same way.

* the steps of the scenarios a task covers (``tasks.md``; a feature without one, such as one on the quick path, is one
  task ``T-<n>.0`` covering every example), resolved to the core instructions of the vocabulary: a screen
  step (``C.UI.*``, the application state) makes it a UI task, an API step an API task, a record or query step a data task;
  a project step counts as the core instructions it composes;
* signing in (``C.ACTOR.AUTH``), or a word about money, credentials or personal data in the rules the task covers or in
  their titles, makes it a security task.

A UI task is written by the ``ui-engineer``, any other by the ``implementer``. Every task is reviewed by the
``code-reviewer``; a UI task also by the ``ui-reviewer``, a security task by the ``security-reviewer``. Each reviewer
writes ``reviews/<task>-<reviewer>.md`` in the feature folder, and the implement gate waits for those reports.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config as cfg
from . import featurefiles, gherkin, reviewlog, roles, store, trace, vocabulary
from .errors import StoreError, UsageError

PLUGIN_ROOT = Path(__file__).resolve().parents[3]
PRACTICES = PLUGIN_ROOT / "cards" / "practices"
REVIEWS_DIR = roles.REVIEWS_DIR
VERDICT = re.compile(r"^\s*Verdict:\s*(PASS|FINDINGS)\b", re.IGNORECASE | re.MULTILINE)

UI_STEPS = ("C.UI.", "C.STATE.GLOBAL", "C.STATE.VERIFY")
API_STEPS = ("C.API.",)
DATA_STEPS = ("C.ENTITY.", "C.QUERY.COUNT")
AUTH_STEPS = ("C.ACTOR.AUTH",)
# Words that make a task a security task when a rule it covers uses them: money, credentials, access and personal data.
SECURITY_WORDS = re.compile(
    r"\b(?:sign(?:s|ed)?[ -]in|log(?:s|ged)?[ -]in|login|logout|password|passwords|token|tokens|session|sessions|"
    r"permission|permissions|authori[sz]\w*|authenticat\w*|role|roles|admin|admins|secret|secrets|api key|"
    r"pay|pays|paid|payment|payments|refund|refunds|charge|charges|invoice|invoices|billing|card number|credit card|"
    r"personal data|email address|phone number|date of birth|address)\b", re.IGNORECASE)
CARDS = {"ui": ("ui-design", "accessibility"), "api": ("api-design",),
         "data": ("database-schema", "database-performance"), "security": ("security",)}
WRITERS, REVIEWERS = roles.WRITERS, roles.REVIEWERS


@dataclass
class Route:
    task: str
    title: str
    writer: str
    reviewers: list[str]
    cards: list[str]
    because: list[str] = field(default_factory=list)


def _instruction_ids(vocab: vocabulary.Vocabulary, step: gherkin.Step, language: str) -> list[str]:
    ids: list[str] = []
    for match in vocab.resolve(step.kind, step.text, language):
        ids += list(match.entry.composes) if match.entry.source == "project" else [match.entry.id]
    return ids


def _scenarios_by_example(root: Path, feature_id: str) -> dict[str, list[tuple[gherkin.Feature, gherkin.Scenario, gherkin.Rule | None]]]:
    found: dict[str, list] = {}
    for path in featurefiles.spec_files(root, feature_id):
        try:
            feature = gherkin.parse(path.read_text(encoding="utf-8-sig"), path.as_posix())
        except gherkin.ParseError:
            continue                                           # `bdd lint` reports it; an unreadable file routes nothing
        for scenario, rule in feature.scenarios():
            for tag in feature.effective_tags(scenario, rule):
                if trace.EXAMPLE_ID.fullmatch(tag.lstrip("@")):
                    found.setdefault(tag.lstrip("@"), []).append((feature, scenario, rule))
    return found


def _steps(feature: gherkin.Feature, scenario: gherkin.Scenario, rule: gherkin.Rule | None) -> list[gherkin.Step]:
    steps = list(feature.background.steps) if feature.background else []
    if rule is not None and rule.background is not None:
        steps += rule.background.steps
    return steps + list(scenario.steps)


def _has(ids: list[str], prefixes: tuple[str, ...]) -> list[str]:
    return sorted({i for i in ids if i.startswith(prefixes)})


def routes(root: Path, feature_dir: Path, feature_id: str) -> list[Route]:
    config = cfg.load(root)
    vocab = vocabulary.load(config.vocabulary_file)
    rules = trace.read_ids(feature_dir / "rules.md", trace.RULE_LINE) or {}
    scenarios = _scenarios_by_example(root, feature_id)
    tasks = trace.read_tasks(feature_dir / "tasks.md") or {}
    claimed = {example for task in tasks.values() for example in task["examples"]}
    unclaimed = sorted((e for e in scenarios if e not in claimed), key=trace._sort_key)
    if unclaimed or not tasks:         # no tasks.md (the quick path), an empty one, or examples no task claims: still routed
        title = "the whole feature" if not tasks else "the examples no task claims"
        reserved = tasks.setdefault(whole_feature_task(feature_id), {"title": title, "examples": []})
        reserved["examples"] = reserved["examples"] + [e for e in unclaimed if e not in reserved["examples"]]   # never overwritten
    out: list[Route] = []
    for task_id, task in tasks.items():
        ids: list[str] = []
        texts: list[str] = []
        for example in task["examples"]:
            rule_id = trace.rule_of(example)
            texts.append(rules.get(rule_id, ""))
            for feature, scenario, rule in scenarios.get(example, []):
                texts += [rule.name if rule else "", scenario.name]
                for step in _steps(feature, scenario, rule):
                    ids += _instruction_ids(vocab, step, feature.language)
        ui, api, data, auth = (_has(ids, p) for p in (UI_STEPS, API_STEPS, DATA_STEPS, AUTH_STEPS))
        words = sorted({m.group(0).casefold() for text in texts for m in SECURITY_WORDS.finditer(text)})
        because = [f"screen steps ({', '.join(ui)})"] if ui else []
        because += [f"API steps ({', '.join(api)})"] if api else []
        because += [f"record steps ({', '.join(data)})"] if data else []
        because += [f"a signed-in actor ({', '.join(auth)})"] if auth else []
        because += [f"the rules mention {', '.join(words)}"] if words else []
        kinds = [k for k, hit in (("ui", ui), ("api", api), ("data", data), ("security", auth or words)) if hit]
        reviewers = ["code-reviewer"] + (["security-reviewer"] if "security" in kinds else []) + (["ui-reviewer"] if ui else [])
        cards = [c for k in kinds for c in CARDS[k] if (PRACTICES / f"{c}.md").is_file()]
        out.append(Route(task_id, task["title"], "ui-engineer" if ui else "implementer", reviewers, cards, because))
    return out


def whole_feature_task(feature_id: str) -> str:
    """The task id that stands for the whole feature when it has no ``tasks.md``: ``T-007.0`` for FEAT-007."""
    return f"T-{feature_id.split('-', 1)[1]}.0"


def review_path(feature_dir: Path, task_id: str, reviewer: str) -> Path:
    return feature_dir / REVIEWS_DIR / f"{task_id}-{reviewer}.md"


def review_problems(root: Path, feature_dir: Path, feature_id: str, hooks_seen: bool = False) -> list[str]:
    """Why the implement gate may not pass yet: a review the routing asks for is missing or has no verdict, or, where the
    hooks run, its content is not what that reviewer wrote to that file (``reviewlog``)."""
    problems: list[str] = []
    log = reviewlog.recorded(root) if hooks_seen else {}
    for route in routes(root, feature_dir, feature_id):
        for reviewer in route.reviewers:
            path = review_path(feature_dir, route.task, reviewer)
            rel = path.relative_to(feature_dir).as_posix()
            if not path.is_file():
                problems.append(f"{route.task} has no {reviewer} report ({rel})")
            elif not VERDICT.search(path.read_text(encoding="utf-8-sig")):
                problems.append(f"{rel} has no 'Verdict: PASS' or 'Verdict: FINDINGS' line")
            elif hooks_seen and not reviewlog.written_by(root, path, reviewer, log):
                problems.append(f"{rel} is not what the {reviewer} agent wrote: a report counts only as its own reviewer "
                                "wrote it, unchanged; run the reviewer again")
    return problems


def describe(route: Route) -> str:
    lines = [f"{route.task} {route.title}".rstrip(), f"  writer: {route.writer}", f"  reviewers: {', '.join(route.reviewers)}",
             f"  cards: {', '.join(route.cards) or '(the language card only)'}"]
    return "\n".join(lines + ([f"  because: {'; '.join(route.because)}"] if route.because else []))


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd route", description="Name the writer, the reviewers and the cards of each task.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--json", action="store_true", help="print the routes as JSON")
    args = ap.parse_args(argv)
    try:
        from .statecmd import project_root
        root = project_root()
        found = routes(root, store.find_feature_dir(root, args.feature), args.feature)
    except (UsageError, StoreError, cfg.ConfigError, vocabulary.VocabularyError) as exc:
        print(f"bdd route: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(r) for r in found], indent=2))
    else:
        print("\n".join(describe(r) for r in found) or f"{args.feature}: tasks.md names no task")
    return 0
