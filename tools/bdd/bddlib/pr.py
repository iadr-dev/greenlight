"""`bdd pr FEAT-n`: a pull-request description built from the feature's recorded state.

    bdd pr FEAT-007                    Markdown on stdout, safe to paste
    bdd pr FEAT-007 --json             the same facts as data
    bdd pr FEAT-007 --output PR.md     write the Markdown to a file inside the project (not under .bdd/)

Everything comes from artifacts and records: the brief, the trace matrix, the state file (gates, approvals,
assumptions, cost), the recorded runs, the quality, mutation and stability results and the auditor's report.
Nothing is estimated and nothing is sent anywhere: the command never talks to a git host. Only counts, short digests
and project-relative names are printed; no command lines, environment values, session or transcript identifiers.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import approvals, classify, enforcement, gates, lockfile, mutation, quality, runner, state, store, trace
from . import config as cfg
from .errors import StoreError, UsageError
from .statecmd import guarded, project_root

SUMMARY_SECTIONS = ("Problem statement", "The ask")
SUMMARY_LIMIT = 700
STABILITY_RESULT = "stability.json"
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING = re.compile(r"^#{1,6}\s*(.*?)\s*$")
_VERDICT = re.compile(r"^Verdict:\s*(PASS|FINDINGS)\b", re.MULTILINE)
_REVIEW = re.compile(r"^Review status:\s*(.+?)\s*$", re.MULTILINE)
_FINDING_GROUPS = (("Must fix", "must_fix"), ("Should fix", "should_fix"), ("Unverifiable", "unverifiable"))
_BULLET = re.compile(r"^\s*[-*]\s+(.*\S)\s*$")


def short(digest: str | None) -> str:
    return digest[:12] if digest else "-"


def read_text(path: Path) -> str:
    return _COMMENT.sub("", path.read_text(encoding="utf-8-sig")) if path.is_file() else ""


def section(text: str, names: tuple[str, ...]) -> str:
    """The body of the first section whose heading is one of ``names``."""
    for name in names:
        body: list[str] = []
        inside = False
        for line in text.splitlines():
            heading = _HEADING.match(line)
            if heading:
                if inside:
                    break
                inside = heading.group(1).casefold() == name.casefold()
            elif inside:
                body.append(line)
        cleaned = " ".join(part.strip().lstrip("> ").strip() for part in body if part.strip())
        if cleaned and not cleaned.startswith("<"):
            return cleaned[:SUMMARY_LIMIT] + ("..." if len(cleaned) > SUMMARY_LIMIT else "")
    return ""


def audit_of(feature_dir: Path) -> dict | None:
    """The auditor's verdict and findings from report.md, or None when there is no report yet."""
    path = feature_dir / "report.md"
    if not path.is_file():
        return None
    text = _COMMENT.sub("", path.read_text(encoding="utf-8-sig"))
    verdict, review = _VERDICT.search(text), _REVIEW.search(text)
    found: dict[str, list[str]] = {key: [] for _, key in _FINDING_GROUPS}
    current = None
    in_findings = False
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading:
            in_findings = heading.group(1).casefold() == "findings"
            current = None
            continue
        if not in_findings:
            continue
        label = next((key for name, key in _FINDING_GROUPS if line.strip().lstrip("-* ").casefold().startswith(name.casefold() + ":")), None)
        if label:
            current = label
            rest = line.split(":", 1)[1].strip()
            if rest:
                found[current].append(rest)
            continue
        bullet = _BULLET.match(line)
        if bullet and current:
            found[current].append(bullet.group(1))
    return {"verdict": verdict.group(1) if verdict else None, "review": review.group(1) if review else None, **found}


def run_summary(root: Path, feature_id: str, record: dict | None, expect: str) -> dict | None:
    """Outcome counts of a recorded run and whether it is a valid red or green."""
    if record is None:
        return None
    counts: dict[str, int] = {}
    for case in record.get("cases", []):
        counts[case["outcome"]] = counts.get(case["outcome"], 0) + 1
    result = {"cases": sum(counts.values()), "outcomes": counts, "inputs": short(record.get("inputs")),
              "at": record.get("at"), "valid": None, "problems": []}
    config = cfg.load(root)
    if config.runs:
        try:
            verdict = classify.classify_run(record, classify.feature_scenarios(root, feature_id), list(config.runs))[expect]
            result["valid"], result["problems"] = verdict["valid"], list(verdict["problems"])
        except UsageError as exc:
            result["problems"] = [str(exc)]
    return result


def evidence_runs(root: Path, feature_dir: Path, data: dict) -> dict:
    feature_id = data["feature"]
    red = latest = None
    try:
        red = runner.load_red(root, feature_id, data.get("red_run"))
    except (UsageError, StoreError, OSError):
        pass
    try:
        latest = runner.load_latest(root, feature_id)
    except (UsageError, StoreError, OSError):
        pass
    kept = data.get("red_run") or {}
    return {"red": run_summary(root, feature_id, red, "red"), "red_digest": short(kept.get("sha256")),
            "latest": run_summary(root, feature_id, latest, "green")}


def checks_of(root: Path, feature_id: str) -> dict:
    """The optional checks, each None when it was never run (or never configured)."""
    out: dict[str, dict | None] = {"quality": None, "mutation": None, "stability": None}
    try:
        data = quality.load_result(root, feature_id)
        if data:
            out["quality"] = {"passed": data["passed"], "checks": [{"name": c.get("name"), "passed": c.get("passed")}
                                                                   for c in data["checks"]]}
    except StoreError:
        pass
    try:
        data = mutation.load_result(root, feature_id)
        if data:
            out["mutation"] = {"passed": data["passed"], "score": data.get("score"), "threshold": data.get("threshold"),
                               "files": len(data.get("files", [])), "note": data.get("note", "")}
    except StoreError:
        pass
    path = runner.runs_dir(root, feature_id) / STABILITY_RESULT
    if path.is_file():
        try:
            data = store.read_json(path, "the stability result")
            if isinstance(data, dict) and isinstance(data.get("passed"), bool):
                flaky = data.get("flaky")
                out["stability"] = {"passed": data["passed"], "runs": data.get("runs"),
                                    "flaky": len(flaky) if isinstance(flaky, (list, dict)) else None}
        except StoreError:
            pass
    return out


def approvals_of(root: Path, data: dict) -> list[dict]:
    rows = []
    for gate in approvals.GATES:
        last = approvals._last(data, gate)
        if last is None:
            continue
        problems = approvals.effective_problems(root, data, gate) if last["decision"] == "approve" else []
        rows.append({"gate": gate, "decision": last["decision"], "origin": last.get("origin"), "at": last.get("at"),
                     "valid": not problems and last["decision"] == "approve", "reason": last.get("reason", "")})
    return rows


def locks_of(root: Path, feature_dir: Path, feature_id: str) -> dict:
    scopes = sorted(lockfile.read_lock(feature_dir, feature_id)["scopes"])
    try:
        problems = gates.lock_problems(root, feature_dir, feature_id) if scopes else []
    except (UsageError, StoreError, OSError) as exc:
        problems = [str(exc)]
    return {"scopes": scopes, "intact": bool(scopes) and not problems, "problems": problems}


def collect(root: Path, feature_dir: Path) -> dict:
    data = state.load(feature_dir)
    feature_id = data["feature"]
    level, reasons = enforcement.classify(root, data)
    matrix = trace.build(root, feature_dir, feature_id)
    autonomy = data["autonomy"]
    return {
        "feature": feature_id, "title": data["title"], "kind": data.get("kind", "feature"), "phase": data["phase"],
        "summary": section(read_text(feature_dir / "brief.md"), SUMMARY_SECTIONS),
        "autonomy": {"level": autonomy["level"], "switches": len(autonomy.get("switches", []))},
        "unreviewed": autonomy["level"] == "autopilot" or any(s.get("to") == "autopilot" for s in autonomy.get("switches", [])),
        "enforcement": {"level": level, "reasons": reasons},
        "trace": {"totals": matrix["totals"], "gaps": matrix["gaps"], "rules": matrix["rules"]},
        "gates": {name: {"result": g["result"], "at": g.get("at")} for name, g in sorted(data["gates"].items())},
        "approvals": approvals_of(root, data), "locks": locks_of(root, feature_dir, feature_id),
        "runs": evidence_runs(root, feature_dir, data), "checks": checks_of(root, feature_id),
        "design": (feature_dir / "design.md").is_file(),
        "assumptions": [{"id": a["id"], "text": a["text"], "rationale": a["rationale"]} for a in data["assumptions"]],
        "changes": len(data.get("changes", [])),
        "audit": audit_of(feature_dir),
        "cost": {phase: {"tokens": c["tokens"], "seconds": round(c["seconds"], 1)} for phase, c in sorted(data["cost"].items())},
    }


# -- Markdown ----------------------------------------------------------------------------
def cell(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def render_matrix(rules: list[dict]) -> list[str]:
    lines = ["| Rule | Example | Scenarios | Tasks |", "|---|---|---|---|"]
    for rule in rules:
        title = f"**{rule['id']}** {cell(rule['text'])}".strip()
        if not rule["examples"]:
            lines.append(f"| {title} | - | - | - |")
        for i, example in enumerate(rule["examples"]):
            scenarios = "; ".join(cell(s["name"]) for s in example["scenarios"]) or "-"
            lines.append(f"| {title if i == 0 else ''} | {example['id']} {cell(example['text'])} | {scenarios} | "
                         f"{', '.join(example['tasks']) or '-'} |")
    return lines


def render_run(label: str, run: dict | None, digest: str = "") -> str:
    if run is None:
        return f"- {label}: no recorded run"
    outcomes = ", ".join(f"{n} {k}" for k, n in sorted(run["outcomes"].items())) or "no cases"
    verdict = "" if run["valid"] is None else (" (valid)" if run["valid"] else " (NOT valid)")
    kept = f", kept as {digest}" if digest and digest != "-" else ""
    return f"- {label}: {run['cases']} case(s): {outcomes}{verdict}; inputs {run['inputs']}{kept}"


def render_checks(checks: dict) -> list[str]:
    lines = []
    quality_result = checks["quality"]
    if quality_result:
        names = ", ".join(f"{c['name']} {'ok' if c['passed'] else 'FAILED'}" for c in quality_result["checks"])
        lines.append(f"- Quality checks: {'passed' if quality_result['passed'] else 'FAILED'} ({names})")
    mutated = checks["mutation"]
    if mutated:
        score = "no score" if mutated["score"] is None else f"{mutated['score']:g}% killed"
        lines.append(f"- Mutation check: {'passed' if mutated['passed'] else 'FAILED'}, {score}, threshold "
                     f"{mutated['threshold']:g}%, {mutated['files']} file(s)" + (f" - {cell(mutated['note'])}" if mutated["note"] else ""))
    stable = checks["stability"]
    if stable:
        lines.append(f"- Stability: {'passed' if stable['passed'] else 'FAILED'}, {stable['runs']} run(s), "
                     f"{stable['flaky'] if stable['flaky'] is not None else '?'} flaky scenario(s)")
    return lines or ["- No quality, mutation or stability check was run."]


def render_audit(audit: dict | None) -> list[str]:
    if audit is None:
        return ["- No audit report yet (the verify phase has not run)."]
    lines = [f"- Verdict: **{audit['verdict'] or 'unknown'}**, review status: {audit['review'] or 'unknown'}"]
    for title, key in (("Must fix", "must_fix"), ("Should fix", "should_fix"), ("Unverifiable", "unverifiable")):
        items = [i for i in audit[key] if i.strip().strip("<>") not in ("", "none")]
        lines.append(f"- {title}: " + ("none" if not items else ""))
        lines += [f"  - {cell(i)}" for i in items]
    return lines


def render(facts: dict) -> str:
    totals = facts["trace"]["totals"]
    out = [f"# {facts['feature']}: {facts['title']}", ""]
    if facts["unreviewed"]:
        out += ["> **UNREVIEWED.** This feature ran under autopilot: no person answered the questions or approved the rules "
                "and examples. Review the assumptions below before merging.", ""]
    out += ["## Summary", "", facts["summary"] or "_The brief has no summary._", ""]
    kind = " (adoption: describes behaviour that already existed)" if facts["kind"] == "adopt" else ""
    out += [f"Phase: **{facts['phase']}**{kind}. Autonomy: {facts['autonomy']['level']}"
            + (f" ({facts['autonomy']['switches']} switch(es))" if facts["autonomy"]["switches"] else "")
            + f". Enforcement: **{facts['enforcement']['level']}**.", ""]
    if facts["enforcement"]["level"] == "soft":
        out += ["Soft enforcement means violations were detected after the fact, not prevented:"]
        out += [f"- {cell(r)}" for r in facts["enforcement"]["reasons"]] + [""]
    out += [f"## Rules and examples ({totals['rules']} rules, {totals['examples']} examples, {totals['scenarios']} scenarios, "
            f"{totals['tasks']} tasks)", ""] + render_matrix(facts["trace"]["rules"]) + [""]
    gaps = facts["trace"]["gaps"]
    out += ["Traceability gaps: " + ("none." if not gaps else "")]
    out += [f"- {g['code']}: {cell(g['message'])}" for g in gaps] + [""]
    out += ["## Evidence", "", "| Gate | Result |", "|---|---|"]
    out += [f"| {name} | {g['result']} |" for name, g in facts["gates"].items()] + [""]
    out += ["Approvals:"]
    out += [f"- {a['gate']}: {a['decision']}d via {a['origin']}" + ("" if a["valid"] or a["decision"] != "approve" else " (NOT valid now)")
            + (f" - {cell(a['reason'])}" if a["reason"] else "") for a in facts["approvals"]] or ["- none recorded"]
    locks = facts["locks"]
    out += ["", "Locks: " + (("intact (" + ", ".join(locks["scopes"]) + ")") if locks["intact"]
                             else ("none" if not locks["scopes"] else "NOT intact")), ""]
    out += [f"- {cell(p)}" for p in locks["problems"]]
    runs = facts["runs"]
    out += ["## Tests", "", render_run("Red (before the code)", runs["red"], runs["red_digest"]),
            render_run("Latest run", runs["latest"]), ""]
    out += ["## Checks", ""] + render_checks(facts["checks"]) + [""]
    if facts["design"]:
        out += ["A design view (`design.md`) accompanies this feature.", ""]
    if facts["assumptions"]:
        out += ["## Assumptions", ""]
        out += [f"- **{a['id']}** {cell(a['text'])} _(because {cell(a['rationale'])})_" for a in facts["assumptions"]] + [""]
    if facts["changes"]:
        out += [f"Approved work was changed {facts['changes']} time(s) through the change flow.", ""]
    out += ["## Audit", ""] + render_audit(facts["audit"]) + [""]
    if facts["cost"]:
        out += ["## Cost", "", "| Phase | Tokens | Seconds |", "|---|---|---|"]
        out += [f"| {phase} | {c['tokens']} | {c['seconds']:g} |" for phase, c in facts["cost"].items()]
        out += [""]
    return "\n".join(out).rstrip() + "\n"


# -- command -----------------------------------------------------------------------------
def output_target(root: Path, name: str, force: bool) -> Path:
    """A file inside the project, outside .bdd/ (CLI-managed data), not overwritten without --force."""
    target = (Path.cwd() / name).resolve()
    base = root.resolve()
    if not target.is_relative_to(base):
        raise UsageError(f"--output must name a file inside {base}")
    if target.is_relative_to((base / cfg.BDD_DIR).resolve()):
        raise UsageError(f"--output may not be inside {cfg.BDD_DIR}/: that folder is managed by the bdd command line")
    if not target.parent.is_dir():
        raise UsageError(f"--output: the folder {target.parent.relative_to(base).as_posix() or '.'} does not exist")
    if target.exists() and (target.is_dir() or not force):
        raise UsageError(f"{target.relative_to(base).as_posix()} exists; use --force to replace a file")
    return target


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd pr", description="A pull-request description from a feature's records.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--json", action="store_true", help="the facts as JSON instead of Markdown")
    ap.add_argument("--output", metavar="FILE", help="write to a file inside the project instead of stdout")
    ap.add_argument("--force", action="store_true", help="with --output: replace an existing file")
    args = ap.parse_args(argv)

    def action() -> int:
        root = project_root()
        feature_dir = store.find_feature_dir(root, args.feature)
        facts = collect(root, feature_dir)
        text = json.dumps(facts, indent=2, ensure_ascii=False) + "\n" if args.json else render(facts)
        if args.output:
            target = output_target(root, args.output, args.force)
            target.write_text(text, encoding="utf-8", newline="\n")
            print(f"{args.feature}: wrote {target.relative_to(root.resolve()).as_posix()}")
        else:
            sys.stdout.write(text)
        return 0

    try:
        return guarded("pr", action)
    except cfg.ConfigError as exc:
        print(f"bdd pr: {exc}", file=sys.stderr)
        return 2
