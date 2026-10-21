"""Reading a test run: what each scenario did, and whether the run is a valid red or a green.

Each failing test case is classified from its failure text with the adapter's patterns:

    test-defect     the test itself is broken (import error, undefined step, fixture crash)
    expected-fail   it fails because the feature is not there yet (assertion mismatch, 404, ``BDD_EXPECTED_MISSING``)
    unknown         a failure no pattern recognises: it blocks, because guessing would let a broken test pass the gate

Defect patterns are checked first. A *valid red* means every scenario of the feature ran and failed as
``expected-fail``; a scenario that passed is only acceptable if it is tagged ``@existing``.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from . import config as cfg
from . import featurefiles, junit, trace
from .errors import UsageError

PASS, EXPECTED, DEFECT, UNKNOWN, SKIPPED = "pass", "expected-fail", "test-defect", "unknown", "skipped"


def classify_case(case: junit.Case, rules: list[cfg.RunRules]) -> str:
    if case.outcome == junit.PASSED:
        return PASS
    if case.outcome == junit.SKIPPED:
        return SKIPPED
    for outcome, patterns in ((DEFECT, [p for r in rules for p in r.test_defect]),
                              (EXPECTED, [p for r in rules for p in r.expected_fail])):
        if any(re.search(p, case.text) for p in patterns):
            return outcome
    return UNKNOWN


def normalise(text: str) -> str:
    """A scenario name or test name reduced to its letters and digits (of any script), so ``test_order_of_1000`` and
    ``Order of 1000`` compare equal and a title written in Chinese or Cyrillic still has something to compare."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold())


def fold(text: str) -> str:
    """``normalise`` with accents removed (``café`` becomes ``cafe``): runners that build a test name from a title often
    transliterate it, and a title typed with or without accents should still match."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
    return normalise(plain)


def id_pattern(example: str | None) -> re.Pattern[str] | None:
    """The example id (``EX-007.1.2``) as it may appear in a test name: ``-``, ``.``, ``_`` or a space between its parts,
    and not part of a longer id (``EX-007.1.2`` is not found in ``EX-007.1.23``)."""
    parts = re.findall(r"[A-Za-z]+|\d+", example or "")
    if len(parts) < 4:
        return None
    return re.compile(r"(?<![0-9A-Za-z])" + r"[-._ ]*".join(re.escape(part) for part in parts) + r"(?![0-9])", re.IGNORECASE)


def scenario_for(name: str, scenarios: list[dict]) -> dict | None:
    """The scenario a test belongs to: the one whose name is contained in the test name (longest wins), compared as
    letters and digits and again without accents; failing that, the one whose example id the test name carries."""
    wanted, wanted_plain = normalise(name), fold(name)
    hits = []
    for scenario in scenarios:
        key, plain = normalise(scenario["name"]), fold(scenario["name"])
        if (key and key in wanted) or (plain and plain in wanted_plain):
            hits.append((max(len(key), len(plain)), scenario))
    if hits:
        return max(hits, key=lambda hit: hit[0])[1]
    named = [s for s in scenarios if (pattern := id_pattern(s.get("example"))) and pattern.search(name)]
    return named[0] if len(named) == 1 else None


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")[:160]


def classify_run(record: dict, scenarios: list[dict], rules: list[cfg.RunRules]) -> dict:
    """Per-scenario results of a recorded run, with the red and green verdicts."""
    results: dict[str, list[dict]] = {}
    unmapped = 0
    for raw in record["cases"]:
        case = junit.Case(raw["name"], raw["classname"], raw["outcome"], raw["text"])
        scenario = scenario_for(case.name, scenarios)
        if scenario is None:
            unmapped += 1
            continue
        results.setdefault(scenario["name"], []).append(
            {"case": case.label, "result": classify_case(case, rules), "detail": first_line(case.text)})
    rows = [scenario_row(s, results.get(s["name"], [])) for s in scenarios]
    return {"feature": record["feature"], "mode": record["mode"], "seed": record["seed"], "at": record["at"],
            "scenarios": rows, "unmapped_cases": unmapped, "red": verdict_red(rows), "green": verdict_green(rows)}


def scenario_row(scenario: dict, cases: list[dict]) -> dict:
    results = [c["result"] for c in cases]
    if not results:
        result = "not-run"
    else:                                                      # the worst outcome wins
        result = next(r for r in (DEFECT, UNKNOWN, EXPECTED, SKIPPED, PASS) if r in results)
    detail = next((c["detail"] for c in cases if c["result"] == result and c["detail"]), "")
    return {"scenario": scenario["name"], "example": scenario["example"], "path": scenario["path"],
            "line": scenario["line"], "existing": scenario["existing"], "result": result, "detail": detail}


def verdict_red(rows: list[dict]) -> dict:
    problems = []
    for row in rows:
        name, result = row["scenario"], row["result"]
        if result == DEFECT:
            problems.append(f'"{name}" is a test defect: {row["detail"]}')
        elif result == UNKNOWN:
            problems.append(f'"{name}" failed for a reason no classifier recognises: {row["detail"]}')
        elif result == PASS and not row["existing"]:
            problems.append(f'"{name}" passed before implementation: it either already works (tag it @existing) '
                            "or it asserts nothing")
        elif result in ("not-run", SKIPPED):
            problems.append(f'"{name}" did not run')
    return {"valid": not problems and bool(rows), "problems": problems or ([] if rows else ["the feature has no scenarios"])}


def verdict_green(rows: list[dict]) -> dict:
    problems = [f'"{r["scenario"]}" is {r["result"]}' + (f": {r['detail']}" if r["detail"] else "")
                for r in rows if r["result"] != PASS]
    return {"valid": not problems and bool(rows), "problems": problems or ([] if rows else ["the feature has no scenarios"])}


def feature_scenarios(root: Path, feature_id: str) -> list[dict]:
    rows, problems = trace.scenario_rows(root, featurefiles.spec_files(root, feature_id))
    if problems:
        raise UsageError("cannot read the feature files: " + "; ".join(p.message for p in problems))
    return rows


def render(report: dict) -> str:
    lines = [f"{report['feature']}: run at {report['at']} ({report['mode']}" + (f", seed {report['seed']}" if report["seed"] else "") + ")"]
    for row in report["scenarios"]:
        lines.append(f"  {row['result']:<13} {row['example'] or '-':<12} {row['scenario']}" + (f"  [{row['detail']}]" if row["detail"] else ""))
    for name in ("red", "green"):
        verdict = report[name]
        lines.append(f"{name}: {'valid' if verdict['valid'] else 'NOT valid'}")
        lines += [f"  - {p}" for p in verdict["problems"]]
    if report["unmapped_cases"]:
        lines.append(f"({report['unmapped_cases']} test case(s) belong to no scenario of this feature and were ignored)")
    return "\n".join(lines)
