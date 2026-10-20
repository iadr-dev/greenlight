"""`bdd pr FEAT-n`: a pull-request description built from the feature's recorded state.

    bdd pr FEAT-007                    Markdown on stdout, safe to paste
    bdd pr FEAT-007 --json             the same facts as data
    bdd pr FEAT-007 --output PR.md     write the Markdown to a new file with that name in the current folder (inside the project, not .bdd/)

Everything comes from artifacts and records: the brief, the trace matrix, the state file (gates, approvals,
assumptions, cost), the recorded runs, the quality, mutation and stability results and the auditor's report.
Nothing is estimated and nothing is sent anywhere: the command never talks to a git host. Only counts, short digests
and project-relative names are printed; no command lines, environment values, session or transcript identifiers.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import approvals, classify, enforcement, gates, lockfile, mutation, quality, runner, state, store, trace
from . import config as cfg
from .errors import StoreError, UsageError
from .statecmd import guarded, project_root

SUMMARY_SECTIONS = ("Problem statement", "The ask")
SUMMARY_LIMIT = 700
STABILITY_RESULT = "stability.json"
DECISION_WORD = {"approve": "approved", "reject": "rejected"}
FINDING_GROUPS = (("Must fix", "must_fix"), ("Should fix", "should_fix"), ("Unverifiable", "unverifiable"))
MAX_HEADING_LEVEL = 6
BULLET_MARKS = ("- ", "* ")


# -- reading the markdown artifacts ---------------------------------------------------------
def strip_comments(text: str) -> str:
    """Remove ``<!-- ... -->`` comments (templates carry instructions in them)."""
    parts = []
    rest = text
    while (start := rest.find("<!--")) != -1:
        end = rest.find("-->", start + 4)
        if end == -1:
            break
        parts.append(rest[:start])
        rest = rest[end + 3:]
    return "".join(parts) + rest


def read_text(path: Path) -> str:
    return strip_comments(path.read_text(encoding="utf-8-sig")) if path.is_file() else ""


def heading_of(line: str) -> str | None:
    """The text of a Markdown heading line, or None for any other line."""
    stripped = line.strip()
    rest = stripped.lstrip("#")
    level = len(stripped) - len(rest)
    if not 1 <= level <= MAX_HEADING_LEVEL or (rest and not rest[0].isspace()):
        return None
    return rest.strip()


def sections(text: str) -> dict[str, list[str]]:
    """The lines under each heading (lower-cased); a heading met twice keeps its first body."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        title = heading_of(line)
        if title is None:
            if current is not None:
                current.append(line)
        else:
            current = found.setdefault(title.casefold(), []) if title.casefold() not in found else None
    return found


def paragraph(lines: list[str]) -> str:
    """The lines joined into one line of text, quotes and blank lines dropped."""
    text = " ".join(part.strip().lstrip("> ").strip() for part in lines if part.strip())
    return "" if text.startswith("<") else text


def section(text: str, names: tuple[str, ...]) -> str:
    """The body of the first of ``names`` that has text, shortened."""
    found = sections(text)
    for name in names:
        body = paragraph(found.get(name.casefold(), []))
        if body:
            return body[:SUMMARY_LIMIT] + ("..." if len(body) > SUMMARY_LIMIT else "")
    return ""


def line_value(text: str, label: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(label):
            return line[len(label):].strip()
    return None


def finding_label(line: str) -> str | None:
    text = line.strip().lstrip("-* ").casefold()
    return next((key for name, key in FINDING_GROUPS if text.startswith(name.casefold() + ":")), None)


def findings(lines: list[str]) -> dict[str, list[str]]:
    """The items under ``Must fix:``, ``Should fix:`` and ``Unverifiable:`` of the report's Findings section."""
    found: dict[str, list[str]] = {key: [] for _, key in FINDING_GROUPS}
    current = None
    for line in lines:
        label = finding_label(line)
        stripped = line.strip()
        if label:
            current = label
            rest = line.split(":", 1)[1].strip()
            if rest:
                found[label].append(rest)
        elif current and stripped[:2] in BULLET_MARKS:
            found[current].append(stripped[2:].strip())
    return found


def audit_of(feature_dir: Path) -> dict | None:
    """The auditor's verdict and findings from report.md, or None when there is no report yet."""
    path = feature_dir / "report.md"
    if not path.is_file():
        return None
    text = read_text(path)
    verdict = line_value(text, "Verdict:")
    return {"verdict": verdict.split()[0] if verdict else None, "review": line_value(text, "Review status:"),
            **findings(sections(text).get("findings", []))}


# -- facts from the records -----------------------------------------------------------------
def short(digest: str | None) -> str:
    return digest[:12] if digest else "-"


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


def evidence_runs(root: Path, data: dict) -> dict:
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


def quality_facts(root: Path, feature_id: str) -> dict | None:
    try:
        data = quality.load_result(root, feature_id)
    except StoreError:
        return None
    if not data:
        return None
    return {"passed": data["passed"], "checks": [{"name": c.get("name"), "passed": c.get("passed")} for c in data["checks"]]}


def mutation_facts(root: Path, feature_id: str) -> dict | None:
    try:
        data = mutation.load_result(root, feature_id)
    except StoreError:
        return None
    if not data:
        return None
    return {"passed": data["passed"], "score": data.get("score"), "threshold": data.get("threshold"),
            "files": len(data.get("files", [])), "note": data.get("note", "")}


def stability_facts(root: Path, feature_id: str) -> dict | None:
    path = runner.runs_dir(root, feature_id) / STABILITY_RESULT
    if not path.is_file():
        return None
    try:
        data = store.read_json(path, "the stability result")
    except StoreError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("passed"), bool):
        return None
    flaky = data.get("flaky")
    return {"passed": data["passed"], "runs": data.get("runs"), "flaky": len(flaky) if isinstance(flaky, (list, dict)) else None}


def checks_of(root: Path, feature_id: str) -> dict:
    """The optional checks, each None when it was never run (or never configured)."""
    return {"quality": quality_facts(root, feature_id), "mutation": mutation_facts(root, feature_id),
            "stability": stability_facts(root, feature_id)}


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
        "runs": evidence_runs(root, data), "checks": checks_of(root, feature_id),
        "design": (feature_dir / "design.md").is_file(),
        "assumptions": [{"id": a["id"], "text": a["text"], "rationale": a["rationale"]} for a in data["assumptions"]],
        "changes": len(data.get("changes", [])),
        "audit": audit_of(feature_dir),
        "cost": {phase: {"tokens": c["tokens"], "seconds": round(c["seconds"], 1)} for phase, c in sorted(data["cost"].items())},
    }


# -- Markdown ---------------------------------------------------------------------------------
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


def verdict_word(valid: bool | None) -> str:
    if valid is None:
        return ""
    return " (valid)" if valid else " (NOT valid)"


def render_run(label: str, run: dict | None, digest: str = "") -> str:
    if run is None:
        return f"- {label}: no recorded run"
    outcomes = ", ".join(f"{n} {k}" for k, n in sorted(run["outcomes"].items())) or "no cases"
    kept = f", kept as {digest}" if digest and digest != "-" else ""
    return f"- {label}: {run['cases']} case(s): {outcomes}{verdict_word(run['valid'])}; inputs {run['inputs']}{kept}"


def passed_word(passed: bool) -> str:
    return "passed" if passed else "FAILED"


def render_checks(checks: dict) -> list[str]:
    lines = []
    if checks["quality"]:
        names = ", ".join(f"{c['name']} {'ok' if c['passed'] else 'FAILED'}" for c in checks["quality"]["checks"])
        lines.append(f"- Quality checks: {passed_word(checks['quality']['passed'])} ({names})")
    mutated = checks["mutation"]
    if mutated:
        score = "no score" if mutated["score"] is None else f"{mutated['score']:g}% killed"
        note = f" - {cell(mutated['note'])}" if mutated["note"] else ""
        lines.append(f"- Mutation check: {passed_word(mutated['passed'])}, {score}, threshold {mutated['threshold']:g}%, "
                     f"{mutated['files']} file(s){note}")
    stable = checks["stability"]
    if stable:
        flaky = "?" if stable["flaky"] is None else stable["flaky"]
        lines.append(f"- Stability: {passed_word(stable['passed'])}, {stable['runs']} run(s), {flaky} flaky scenario(s)")
    return lines or ["- No quality, mutation or stability check was run."]


def render_audit(audit: dict | None) -> list[str]:
    if audit is None:
        return ["- No audit report yet (the verify phase has not run)."]
    lines = [f"- Verdict: **{audit['verdict'] or 'unknown'}**, review status: {audit['review'] or 'unknown'}"]
    for title, key in FINDING_GROUPS:
        items = [i for i in audit[key] if i.strip().strip("<>") not in ("", "none")]
        lines.append(f"- {title}: " + ("" if items else "none"))
        lines += [f"  - {cell(i)}" for i in items]
    return lines


def render_header(facts: dict) -> list[str]:
    out = [f"# {facts['feature']}: {facts['title']}", ""]
    if facts["unreviewed"]:
        out += ["> **UNREVIEWED.** This feature ran under autopilot: no person answered the questions or approved the rules "
                "and examples. Review the assumptions below before merging.", ""]
    out += ["## Summary", "", facts["summary"] or "_The brief has no summary._", ""]
    kind = " (adoption: describes behaviour that already existed)" if facts["kind"] == "adopt" else ""
    switches = f" ({facts['autonomy']['switches']} switch(es))" if facts["autonomy"]["switches"] else ""
    out += [f"Phase: **{facts['phase']}**{kind}. Autonomy: {facts['autonomy']['level']}{switches}. "
            f"Enforcement: **{facts['enforcement']['level']}**.", ""]
    if facts["enforcement"]["level"] == "soft":
        out += ["Soft enforcement means violations were detected after the fact, not prevented:"]
        out += [f"- {cell(r)}" for r in facts["enforcement"]["reasons"]] + [""]
    return out


def render_trace(facts: dict) -> list[str]:
    totals = facts["trace"]["totals"]
    gaps = facts["trace"]["gaps"]
    out = [f"## Rules and examples ({totals['rules']} rules, {totals['examples']} examples, {totals['scenarios']} scenarios, "
           f"{totals['tasks']} tasks)", ""] + render_matrix(facts["trace"]["rules"]) + [""]
    out += ["Traceability gaps: none." if not gaps else "Traceability gaps:"]
    return out + [f"- {g['code']}: {cell(g['message'])}" for g in gaps] + [""]


def approval_line(approval: dict) -> str:
    word = DECISION_WORD.get(approval["decision"], approval["decision"])
    stale = " (NOT valid now)" if approval["decision"] == "approve" and not approval["valid"] else ""
    reason = f" - {cell(approval['reason'])}" if approval["reason"] else ""
    return f"- {approval['gate']}: {word} via {approval['origin']}{stale}{reason}"


def lock_word(locks: dict) -> str:
    if not locks["scopes"]:
        return "none"
    return "intact (" + ", ".join(locks["scopes"]) + ")" if locks["intact"] else "NOT intact"


def render_evidence(facts: dict) -> list[str]:
    out = ["## Evidence", "", "| Gate | Result |", "|---|---|"]
    out += [f"| {name} | {g['result']} |" for name, g in facts["gates"].items()] + ["", "Approvals:"]
    out += [approval_line(a) for a in facts["approvals"]] or ["- none recorded"]
    locks = facts["locks"]
    out += ["", f"Locks: {lock_word(locks)}", ""]
    if locks["problems"]:
        out += [f"- {cell(p)}" for p in locks["problems"]] + [""]
    runs = facts["runs"]
    return out + ["## Tests", "", render_run("Red (before the code)", runs["red"], runs["red_digest"]),
                  render_run("Latest run", runs["latest"]), "", "## Checks", ""] + render_checks(facts["checks"]) + [""]


def render_tail(facts: dict) -> list[str]:
    out = ["A design view (`design.md`) accompanies this feature.", ""] if facts["design"] else []
    if facts["assumptions"]:
        out += ["## Assumptions", ""]
        out += [f"- **{a['id']}** {cell(a['text'])} _(because {cell(a['rationale'])})_" for a in facts["assumptions"]] + [""]
    if facts["changes"]:
        out += [f"Approved work was changed {facts['changes']} time(s) through the change flow.", ""]
    out += ["## Audit", ""] + render_audit(facts["audit"]) + [""]
    if facts["cost"]:
        out += ["## Cost", "", "| Phase | Tokens | Seconds |", "|---|---|---|"]
        out += [f"| {phase} | {c['tokens']} | {c['seconds']:g} |" for phase, c in facts["cost"].items()] + [""]
    return out


def render(facts: dict) -> str:
    lines = render_header(facts) + render_trace(facts) + render_evidence(facts) + render_tail(facts)
    return "\n".join(lines).rstrip() + "\n"


# -- command ------------------------------------------------------------------------------------
def output_target(root: Path, name: str, force: bool) -> str:
    """The path of a new file called ``name`` in the current folder, which must be inside the project but not under .bdd/
    (CLI-managed data). Only a file name is accepted, so the path cannot be steered; an existing file needs --force."""
    safe = os.path.basename(name)
    if not safe or safe != name or safe in (os.curdir, os.pardir):
        raise UsageError("--output takes a file name, written in the current folder; it is not a path")
    base, folder = os.path.realpath(root), os.path.realpath(os.getcwd())
    if os.path.commonpath([base, folder]) != base:
        raise UsageError(f"--output writes in the current folder, which must be inside {base}")
    inside = os.path.relpath(folder, base).replace(os.sep, "/")
    if inside == cfg.BDD_DIR or inside.startswith(cfg.BDD_DIR + "/"):
        raise UsageError(f"--output may not write inside {cfg.BDD_DIR}/: that folder is managed by the bdd command line")
    target = os.path.join(folder, safe)
    if os.path.isdir(target) or (os.path.exists(target) and not force):
        raise UsageError(f"{safe} exists; use --force to replace a file")
    return target


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd pr", description="A pull-request description from a feature's records.")
    ap.add_argument("feature", help="feature id, e.g. FEAT-007")
    ap.add_argument("--json", action="store_true", help="the facts as JSON instead of Markdown")
    ap.add_argument("--output", metavar="NAME", help="write to a file with this name in the current folder (inside the project)")
    ap.add_argument("--force", action="store_true", help="with --output: replace an existing file")
    args = ap.parse_args(argv)

    def action() -> int:
        root = project_root()
        facts = collect(root, store.find_feature_dir(root, args.feature))
        text = json.dumps(facts, indent=2, ensure_ascii=False) + "\n" if args.json else render(facts)
        if not args.output:
            sys.stdout.write(text)
            return 0
        target = output_target(root, args.output, args.force)
        try:
            Path(target).write_text(text, encoding="utf-8", newline="\n")
        except OSError as exc:
            print(f"bdd pr: cannot write {args.output}: {exc.strerror or exc}", file=sys.stderr)
            return 2
        print(f"{args.feature}: wrote {args.output}")
        return 0

    try:
        return guarded("pr", action)
    except cfg.ConfigError as exc:
        print(f"bdd pr: {exc}", file=sys.stderr)
        return 2
