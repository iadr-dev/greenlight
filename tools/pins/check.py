#!/usr/bin/env python3
"""Pinned versions that are out of date or near their end of life, as a report (and, in CI, one issue kept up to date).

    python tools/pins/check.py [--json] [--strict] [--issue]

Dependabot (``.github/dependabot.yml``) keeps the packages and the workflows' actions current. This script covers what it
does not see:

* the language and runtime versions named in the workflows and the adapters' CI templates (``node-version: "22"`` and
  the like), against the end-of-life dates of https://endoflife.date;
* the actions pinned in the adapters' CI templates and ``ci.md`` snippets, which are not under ``.github/workflows``;
* the NuGet packages of the .NET adapter, whose lock file ships under another name (``packages.lock.json.template``).

A pin that could not be checked (no network, an unknown product) is listed as such, never as fine. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOON = 180                       # days before an end-of-life date that a pin is reported
TIMEOUT = 20
ACCEPTED = Path(__file__).with_name("accepted.toml")
ISSUE_TITLE = "Pinned versions: out of date or near end of life"
ISSUE_LABEL = "pins"

RUNTIME_KEYS = {"node-version": "nodejs", "python-version": "python", "go-version": "go", "java-version": "eclipse-temurin",
                "dotnet-version": "dotnet"}
RUNTIME = re.compile(r"(?m)^\s*-?\s*(?P<key>" + "|".join(RUNTIME_KEYS) + r")\s*:\s*[\"']?(?P<value>\d+(?:\.\d+)*(?:\.x)?)[\"']?")
ACTION = re.compile(r"uses:\s*(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?P<path>(?:/[A-Za-z0-9_./-]+)?)@(?P<sha>[0-9a-f]{40})"
                    r"\s*#\s*v?(?P<version>\d+(?:\.\d+)*)")
NUGET = re.compile(r'<PackageReference\s+Include="(?P<id>[^"]+)"\s+Version="(?P<version>[^"]+)"')


@dataclass(frozen=True)
class Finding:
    kind: str            # runtime | action | package
    what: str
    where: str
    pinned: str
    detail: str
    level: str           # eol | behind | unchecked


def fetch_json(url: str):
    """The parsed JSON at ``url``, or None when it cannot be had (a network error, a status other than 200, bad JSON)."""
    request = urllib.request.Request(url, headers={"User-Agent": "greenlight-pins", "Accept": "application/json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def numeric(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", version.split("-", 1)[0]))


def files(root: Path) -> list[Path]:
    found = sorted((root / ".github" / "workflows").glob("*.yml")) + sorted(root.glob("adapters/*/ci/github-actions.yml"))
    return found + sorted(root.glob("adapters/*/ci.md"))


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def runtime_findings(root: Path, fetch, today: datetime.date) -> list[Finding]:
    uses: dict[tuple[str, str], list[str]] = {}
    for path in files(root):
        for m in RUNTIME.finditer(path.read_text(encoding="utf-8", errors="replace")):
            uses.setdefault((m["key"], m["value"]), []).append(rel(root, path))
    out: list[Finding] = []
    cycles: dict[str, object] = {}
    for (key, value), places in sorted(uses.items()):
        product = RUNTIME_KEYS[key]
        where = f"{places[0]}" + (f" and {len(places) - 1} more" if len(places) > 1 else "")
        table = cycles.setdefault(product, fetch(f"https://endoflife.date/api/{product}.json"))
        if not isinstance(table, list):
            out.append(Finding("runtime", f"{product} {value}", where, value, "could not be checked (no answer from endoflife.date)", "unchecked"))
            continue
        cycle = value[:-2] if value.endswith(".x") else value
        names = [".".join(cycle.split(".")[:n]) for n in range(len(cycle.split(".")), 0, -1)]      # "10.0" is cycle "10" for .NET
        row = next((r for name in names for r in table if str(r.get("cycle")) == name), None)
        if row is None:
            out.append(Finding("runtime", f"{product} {value}", where, value, "not a release cycle endoflife.date knows", "unchecked"))
            continue
        eol = row.get("eol")
        if eol is True:
            out.append(Finding("runtime", f"{product} {value}", where, value, "has reached end of life", "eol"))
        elif isinstance(eol, str):
            try:
                ends = datetime.date.fromisoformat(eol)
            except ValueError:
                continue
            if ends <= today:
                out.append(Finding("runtime", f"{product} {value}", where, value, f"reached end of life on {eol}", "eol"))
            elif (ends - today).days <= SOON:
                out.append(Finding("runtime", f"{product} {value}", where, value, f"reaches end of life on {eol}", "eol"))
    return out


def action_findings(root: Path, fetch) -> list[Finding]:
    pinned: dict[str, dict] = {}
    for path in files(root):
        if path.parent.name == "workflows" and path.parent.parent.name == ".github":
            continue                                        # Dependabot's: the workflows of this repository
        for m in ACTION.finditer(path.read_text(encoding="utf-8", errors="replace")):
            entry = pinned.setdefault(m["repo"], {"version": m["version"], "places": []})
            if numeric(m["version"]) < numeric(entry["version"]):
                entry["version"] = m["version"]              # report the oldest pin of an action
            entry["places"].append(rel(root, path))
    out: list[Finding] = []
    for repo, entry in sorted(pinned.items()):
        release = fetch(f"https://api.github.com/repos/{repo}/releases/latest")
        where = entry["places"][0] + (f" and {len(set(entry['places'])) - 1} more files" if len(set(entry["places"])) > 1 else "")
        if not isinstance(release, dict) or not release.get("tag_name"):
            out.append(Finding("action", repo, where, entry["version"], "could not be checked (no answer from GitHub)", "unchecked"))
        elif numeric(str(release["tag_name"])) > numeric(entry["version"]):
            out.append(Finding("action", repo, where, entry["version"], f"latest release is {release['tag_name']}", "behind"))
    return out


def package_findings(root: Path, fetch) -> list[Finding]:
    out: list[Finding] = []
    for path in sorted(root.glob("adapters/dotnet-reqnroll/templates/tests/*.csproj")):
        for m in NUGET.finditer(path.read_text(encoding="utf-8", errors="replace")):
            listing = fetch(f"https://api.nuget.org/v3-flatcontainer/{m['id'].lower()}/index.json")
            versions = [v for v in (listing or {}).get("versions", []) if "-" not in v] if isinstance(listing, dict) else []
            if not versions:
                out.append(Finding("package", m["id"], rel(root, path), m["version"], "could not be checked (no answer from NuGet)", "unchecked"))
                continue
            latest = max(versions, key=numeric)
            if numeric(latest) > numeric(m["version"]):
                out.append(Finding("package", m["id"], rel(root, path), m["version"], f"latest release is {latest}", "behind"))
    return out


def accepted(path: Path = ACCEPTED) -> dict[tuple[str, str], str]:
    """{(what, pinned): reason} for the pins that are behind on purpose. An entry stops applying when the pin changes."""
    if not path.is_file():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return {(str(e["what"]), str(e["pinned"])): str(e["reason"]) for e in data.get("accepted", []) if e.get("reason")}


def check(root: Path = REPO, fetch=fetch_json, today: datetime.date | None = None, holds: dict | None = None) -> list[Finding]:
    today = today or datetime.date.today()
    found = runtime_findings(root, fetch, today) + action_findings(root, fetch) + package_findings(root, fetch)
    held = accepted() if holds is None else holds
    return [f for f in found if (f.what, f.pinned) not in held]


def report(findings: list[Finding]) -> str:
    if not findings:
        return "Every pin checked is current and none is near its end of life."
    titles = {"eol": "Past or near end of life", "behind": "A newer release exists", "unchecked": "Could not be checked"}
    lines = ["Dependabot keeps packages and the workflows' actions current; these are the pins it does not see.", ""]
    for level in ("eol", "behind", "unchecked"):
        group = [f for f in findings if f.level == level]
        if group:
            lines += [f"### {titles[level]}", ""] + [f"- **{f.what}** ({f.kind}, pinned `{f.pinned}`) in `{f.where}`: {f.detail}" for f in group] + [""]
    return "\n".join(lines).rstrip() + "\n"


def keep_issue(findings: list[Finding], run=subprocess.run) -> str:
    """One open issue holds the report: created or updated while there is something to say, closed when there is not."""
    def gh(*args: str) -> subprocess.CompletedProcess:
        return run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    gh("label", "create", ISSUE_LABEL, "--color", "fbca04", "--description", "Pinned versions to look at", "--force")
    listing = gh("issue", "list", "--label", ISSUE_LABEL, "--state", "open", "--json", "number", "--limit", "1")
    try:
        number = (json.loads(listing.stdout or "[]") or [{}])[0].get("number")
    except ValueError:
        number = None
    actionable = [f for f in findings if f.level != "unchecked"] or [f for f in findings]
    if not findings:
        if number:
            gh("issue", "close", str(number), "--comment", "Every pin checked is current now.")
            return f"closed issue #{number}"
        return "nothing to report"
    body = report(actionable)
    if number:
        gh("issue", "edit", str(number), "--body", body)
        return f"updated issue #{number}"
    gh("issue", "create", "--title", ISSUE_TITLE, "--label", ISSUE_LABEL, "--body", body)
    return "opened an issue"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Report pinned versions that are out of date or near end of life.")
    ap.add_argument("--json", action="store_true", help="print the findings as JSON")
    ap.add_argument("--strict", action="store_true", help="exit 1 when there is a finding that is not just unchecked")
    ap.add_argument("--issue", action="store_true", help="create, update or close the one issue that holds the report (needs gh)")
    args = ap.parse_args(argv)
    findings = check()
    print(json.dumps([asdict(f) for f in findings], indent=2) if args.json else report(findings))
    if args.issue:
        print(keep_issue(findings))
    return 1 if args.strict and any(f.level != "unchecked" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
