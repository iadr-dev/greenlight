"""Metrics of one finished run, read from the project's own records (never from the conversation), and the summary table.

    python evals/collect.py [NAME.jsonl ...]      print the summary table of stored rows (files in evals/results/)

`collect_row` takes a *reader*: a callable that runs one `bdd` command in the project and returns (exit code, stdout).
The harness passes a real one; the tests pass canned output, so nothing here needs a model.

The targets a release is held to are in TARGETS and in evals/README.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

Reader = Callable[..., tuple[int, str]]

# metric -> (comparison, value). "min": the measured value must be at least this; "max": at most this.
TARGETS = {
    "rules_with_examples_pct": ("min", 100.0),
    "valid_red_pct": ("min", 90.0),
    "green_pct": ("min", 80.0),
    "locked_spec_violations": ("max", 0),
    "vocabulary_resolution_pct": ("min", 100.0),
    "forged_approvals": ("max", 0),
}
STEP_LINE = re.compile(r"^\s*(?:Given|When|Then|And|But)\s", re.IGNORECASE | re.MULTILINE)
UNRESOLVED_CODES = ("L002", "L003")
BAD_APPROVAL_WORDS = ("invalid", "unverifiable")
VERDICT = re.compile(r"^\s*Verdict:\s*(PASS|FINDINGS)\b", re.IGNORECASE | re.MULTILINE)


SKIPPED = {".venv", "venv", "node_modules", ".git"}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def pct(part: int, whole: int) -> float | None:
    return round(100.0 * part / whole, 1) if whole else None


def load_json(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def rules_with_examples_pct(trace: dict) -> float | None:
    rules = trace.get("rules") or []
    return pct(sum(1 for r in rules if r.get("examples")), len(rules))


def vocabulary_pct(lint: dict, feature_text: str) -> float | None:
    steps = len(STEP_LINE.findall(feature_text))
    unresolved = sum(1 for i in lint.get("issues", []) if i.get("code") in UNRESOLVED_CODES)
    return pct(max(steps - unresolved, 0), steps)


def forged_approvals(verify_output: str) -> int:
    """Approvals the transcript check calls invalid or unverifiable (a forged one is one of these)."""
    return sum(1 for line in verify_output.splitlines() if any(w in line.casefold() for w in BAD_APPROVAL_WORDS))


def lock_violations(lock_output: str) -> int:
    return sum(1 for line in lock_output.splitlines() if re.search(r"\b(changed|added|missing)\b", line))


def auditor_verdict(report_text: str) -> str | None:
    match = VERDICT.search(report_text)
    return match.group(1).upper() if match else None


def seconds_per_phase(state: dict) -> dict[str, float]:
    return {phase: entry.get("seconds", 0.0) for phase, entry in (state.get("cost") or {}).items()}


def tokens_total(state: dict) -> int:
    return sum(entry.get("tokens", 0) for entry in (state.get("cost") or {}).values())


def assumption_agreement(assumptions: list[dict], answers: list[dict]) -> dict | None:
    """Compare recorded assumptions with the scripted answers of a request.

    An answer is {"id", "about": [words that find the assumption], "expect": [words the right one contains]}.
    Agreed: an assumption about it states what is expected; disagreed: one about it does not; unanswered: none."""
    if not answers:
        return None
    texts = [f"{a.get('text', '')} {a.get('rationale', '')}".casefold() for a in assumptions]
    agreed = disagreed = 0
    for answer in answers:
        about = [w.casefold() for w in answer.get("about", [])]
        expect = [w.casefold() for w in answer.get("expect", [])]
        found = [t for t in texts if all(w in t for w in about)]
        if found and any(all(w in t for w in expect) for t in found):
            agreed += 1
        elif found:
            disagreed += 1
    return {"agreed": agreed, "disagreed": disagreed, "unanswered": len(answers) - agreed - disagreed,
            "agreement_pct": pct(agreed, len(answers))}


CARD_PATH = re.compile(r"cards[\\/]+((?:techniques|practices|instructions|runners)[\\/]+[\w.\-]+\.md)")
READING_TOOLS = ("Read", "Bash", "Grep", "Glob")          # a card is read when one of these names it; Write and Edit only produce files


def transcript_files(transcript: Path) -> list[Path]:
    """The session's transcript and those of the subagents it started: the agents, not the orchestrator, read the cards."""
    return [transcript, *sorted((transcript.with_suffix("") / "subagents").glob("agent-*.jsonl"))]


def strings_of(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in strings_of(item)]
    if isinstance(value, list):
        return [text for item in value for text in strings_of(item)]
    return []


def cards_in(line: str) -> set[str]:
    """Cards named by the reading tool uses (Read, Bash, Grep, Glob) of one transcript line."""
    try:
        content = (json.loads(line).get("message") or {}).get("content")
    except (ValueError, AttributeError):
        return set()
    found: set[str] = set()
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") in READING_TOOLS:
            for text in strings_of(block.get("input")):
                found.update(re.sub(r"[\\/]+", "/", m.group(1)) for m in CARD_PATH.finditer(text))
    return found


def cards_read(transcript: Path | None) -> list[str] | None:
    """Card files the session and its subagents read, from their transcripts (JSON lines); None when there is no transcript."""
    if transcript is None or not transcript.is_file():
        return None
    found: set[str] = set()
    for path in transcript_files(transcript):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            found |= cards_in(line)
    return sorted(found)


def path_key(path: Path) -> str:
    """A comparison key for a path: absolute, normalised and, on Windows, case-folded."""
    return os.path.normcase(os.path.abspath(path))


def foreign_violations(project: Path, private: list[Path]) -> list[str]:
    """The open integrity violations that name a file outside the run's project and its private folders: a change made by
    other work on the machine while the run was going, not by the run. Relative paths (locked files) are the project's."""
    data = load_json(read_text(project / ".bdd" / ".integrity" / "violations.json"))
    inside = [path_key(p) for p in (project, *private)]
    found = []
    for item in data.get("items") or []:
        where = str(item.get("path") or "") if isinstance(item, dict) and item.get("open") else ""
        if not where or not Path(where).is_absolute():
            continue
        key = path_key(Path(where))
        if not any(key == root or key.startswith(root.rstrip(os.sep) + os.sep) for root in inside):
            found.append(where)
    return sorted(found)


def collect_row(bdd: Reader, project: Path, answers: list[dict] | None = None, transcript: Path | None = None) -> dict:
    """One metrics row from a finished project. ``bdd(*args)`` runs a bdd command in it."""
    status = load_json(bdd("status", "--json")[1])
    features = status.get("features") or []
    row: dict = {"features": len(features), "open_violations": status.get("open_violations")}
    if not features:
        return row
    feature = features[0]["feature"]
    state = load_json(bdd("state", "show", feature, "--json")[1])
    trace = load_json(bdd("trace", feature, "--json")[1])
    classify = load_json(bdd("classify", feature, "--json")[1])
    red = load_json(bdd("classify", feature, "--run", "red", "--json")[1])
    lock_code, lock_text = bdd("lock", feature, "--check", "--require")
    lint = load_json(bdd("lint", "--json")[1])
    verify_text = bdd("approve", feature, "--verify")[1]
    phases = seconds_per_phase(state)
    report_text = read_text(project / ".bdd" / "features" / features[0].get("dir", "") / "report.md")
    features_text = "\n".join(read_text(p) for p in sorted(project.rglob("*.feature")) if not SKIPPED.intersection(p.parts))
    gates = {name: g.get("result") for name, g in (state.get("gates") or {}).items()}
    violations = (status.get("open_violations") or 0) + (lock_violations(lock_text) if lock_code else 0)
    row.update({
        "feature": feature, "phase": state.get("phase"), "autonomy": (state.get("autonomy") or {}).get("level"),
        "enforcement": (state.get("enforcement") or {}).get("level"), "gates": gates,
        "rules_with_examples_pct": rules_with_examples_pct(trace),
        "trace_gaps": [g.get("code") for g in trace.get("gaps", [])],
        "valid_red_pct": 100.0 if (red.get("red") or {}).get("valid") else (0.0 if state.get("red") or gates.get("bind") else None),
        "green_pct": 100.0 if (classify.get("green") or {}).get("valid") else (0.0 if gates.get("implement") else None),
        "locked_spec_violations": violations,
        "vocabulary_resolution_pct": vocabulary_pct(lint, features_text),
        "forged_approvals": forged_approvals(verify_text),
        "tokens": tokens_total(state), "seconds_per_phase": phases,
        "cost_recorded": bool(state.get("cost")),
        "auditor_verdict": auditor_verdict(report_text),
        "assumptions": len(state.get("assumptions", [])),
        "assumption_agreement": assumption_agreement(state.get("assumptions", []), answers or []),
        "cards_read": cards_read(transcript),
    })
    return row


def meets(metric: str, value: float | None) -> str:
    """'ok', 'MISS' or '-' (not measured) for a value against its target."""
    if value is None or metric not in TARGETS:
        return "-"
    kind, target = TARGETS[metric]
    return "ok" if (value >= target if kind == "min" else value <= target) else "MISS"


def mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def summary_table(rows: list[dict]) -> str:
    """Rows grouped by (arm, autonomy, hooks, model): mean of each target metric, with ok/MISS against the target.
    A contaminated row (other work on the machine changed what the run's tripwire watched) is not counted; it is listed
    under the table with the files that were changed."""
    counted = [r for r in rows if not r.get("contaminated")]
    table = targets_table(counted)
    left_out = [r for r in rows if r.get("contaminated")]
    if not left_out:
        return table
    lines = [table, "", f"not counted: {len(left_out)} run(s) where a file outside the run changed during it"]
    for row in left_out:
        lines.append(f"  run {row.get('run')} ({row.get('arm')}, {row.get('autonomy_requested')}): "
                     + ", ".join(row.get("foreign_violations") or []))
    return "\n".join(lines)


def targets_table(rows: list[dict]) -> str:
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row.get("arm", "plugin"), row.get("autonomy_requested", row.get("autonomy")),
                           row.get("hooks", "on"), row.get("model")), []).append(row)
    head = ["arm", "autonomy", "hooks", "model", "runs", *TARGETS, "tokens", "usd"]
    lines = [head]
    for key, members in sorted(groups.items(), key=lambda item: tuple(str(k) for k in item[0])):
        cells = [str(k) for k in key] + [str(len(members))]
        for metric in TARGETS:
            value = mean([r[metric] for r in members if r.get(metric) is not None])
            cells.append("-" if value is None else f"{value:g} {meets(metric, value)}")
        cells.append(str(sum(r.get("tokens") or 0 for r in members)))
        cells.append(f"{sum((r.get('claude') or {}).get('total_cost_usd') or 0 for r in members):.2f}")
        lines.append(cells)
    widths = [max(len(line[i]) for line in lines) for i in range(len(head))]
    return "\n".join("  ".join(cell.ljust(w) for cell, w in zip(line, widths)).rstrip() for line in lines)


def read_rows(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


RESULTS = Path(__file__).resolve().parent / "results"
ROW_FILE = re.compile(r"[\w.-]+\.jsonl")


def main(argv: list[str]) -> int:
    """Summarise result files by name; they are looked up in evals/results/ only, never by a path."""
    bad = [a for a in argv if not ROW_FILE.fullmatch(a)]
    if bad:
        print(f"not a result file name: {', '.join(bad)} (give names of files in evals/results/)")
        return 2
    paths = [RESULTS / a for a in argv] or sorted(RESULTS.glob("*.jsonl"))
    missing = [p.name for p in paths if not p.is_file()]
    if not paths or missing:
        print("no result files (run evals/run_e2e.py first)" if not paths else f"not found in evals/results/: {', '.join(missing)}")
        return 2
    print(summary_table(read_rows(paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
