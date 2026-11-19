"""The known risks a task's code must handle, named before the code is written and answered by the code reviewer.

The list is fixed (``RISKS``): the failures that late audits keep finding in code that passed its scenarios, such as two
sign-ins racing to link one account, a missing rate limit or a storage error shown raw. ``bdd route`` names the risks of
each task from three sources:

* the words of the rules the task covers and of their titles and scenario names (``sign in`` raises concurrent writes,
  rate limits and authorisation);
* the steps of its scenarios (a signed-in actor raises authorisation, a record step storage errors, a query count large
  lists, a clock step time zones);
* the rows of the technical design (``designsections``) for a task with server-side code: a rate limit, authorisation or
  personal data row of *Security and privacy*, a conflict or retry row of *Errors and resilience*, a table, migration,
  query or volume of *Data and performance*; and a date or time zone among the task's building blocks.

The orchestrator copies them into the task's ``Risks:`` line of ``tasks.md`` and may add more; a word that is not a risk
of the list is reported (``bdd trace`` gap ``T010``). The code reviewer's report answers each risk of its task on a line
of its own, ``Risk <name>: handled in <file:line>``, ``Risk <name>: not applicable: <reason>`` or ``Risk <name>:
missing``, and the implement gate refuses a report that leaves one out or says it is missing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

MIN_REASON = 8


def _words(*words: str) -> re.Pattern:
    """A pattern for whole words: a space matches a space or a hyphen, a trailing ``*`` any ending."""
    def one(word: str) -> str:
        stem = word.removesuffix("*")
        text = r"[ -]".join(re.escape(part) for part in stem.split(" "))
        return text + (r"\w*" if word.endswith("*") else "")
    return re.compile(r"\b(?:" + "|".join(one(w) for w in words) + r")\b", re.IGNORECASE)


SIGN_IN = ("sign in", "signs in", "signed in", "signing in", "sign up", "signs up", "signed up", "log in", "logs in",
           "logged in", "login*", "logout", "password*")


@dataclass(frozen=True)
class Risk:
    name: str
    words: re.Pattern                       # words of the task's rules and scenario names that raise it
    steps: tuple[str, ...] = ()             # instruction ids (prefixes) of its steps that raise it
    aliases: tuple[str, ...] = ()           # other spellings accepted on a Risks: line


RISKS = (
    Risk("concurrent writes", _words(*SIGN_IN, "link", "links", "linked", "linking", "concurren*", "at the same time",
                                     "simultaneous*", "twice", "race*", "reserv*", "book", "books", "booked", "booking*",
                                     "stock", "balance*", "counter*", "invite*"),
         aliases=("concurrency", "race conditions", "races")),
    Risk("retries and idempotency", _words("retry", "retries", "retried", "again", "duplicate*", "idempoten*", "webhook*",
                                           "pay", "pays", "paid", "payment*", "charge*", "refund*", "import*", "sync*",
                                           "submit*"), aliases=("retries", "idempotency", "retry")),
    Risk("rate limits", _words(*SIGN_IN, "one-time code*", "verification code*", "otp", "reset*", "invite*", "search*",
                               "api key*", "upload*"), aliases=("rate limit", "rate limiting")),
    Risk("unmapped storage errors", _words("save", "saves", "saved", "saving", "store", "stores", "stored", "storing",
                                           "database*", "upload*", "import*"), steps=("C.ENTITY.",),
         aliases=("storage errors", "unmapped errors")),
    Risk("authorisation", _words(*SIGN_IN, "permission*", "authoris*", "authoriz*", "role", "roles", "admin*", "owner*",
                                 "private", "share", "shared", "sharing", "member*"), steps=("C.ACTOR.AUTH",),
         aliases=("authorization", "access control")),
    Risk("personal data", _words("email*", "e-mail*", "phone*", "address*", "date of birth", "birthday*", "personal",
                                 "profile*", "passport*", "location*", "contact*"), aliases=("privacy", "pii")),
    Risk("time zones", _words("date", "dates", "time zone*", "timezone*", "deadline*", "schedul*", "midnight", "expir*",
                              "daily", "weekly", "monthly", "calendar*", "today", "tomorrow", "yesterday", "reminder*"),
         steps=("C.CLOCK.",), aliases=("time zone", "timezones", "timezone")),
    Risk("large lists", _words("list", "lists", "listing*", "search*", "export*", "history", "feed", "pagination", "paged",
                               "per page", "report*"), steps=("C.QUERY.COUNT",), aliases=("large list", "pagination")),
)
NAMES = tuple(r.name for r in RISKS)
_BY_SPELLING = {spelling: r.name for r in RISKS for spelling in (r.name, *r.aliases)}
NONE_WORDS = {"", "none", "-", "n/a"}


def ordered(names: set[str]) -> list[str]:
    return [n for n in NAMES if n in names]


def parse_line(text: str) -> tuple[list[str], list[str]]:
    """A ``Risks:`` line of tasks.md as (the risks it names, the words that are not risks)."""
    known: set[str] = set()
    unknown: list[str] = []
    for part in re.split(r"[,;]", text):
        word = " ".join(part.strip(" .*_`").casefold().split())
        if word in NONE_WORDS:
            continue
        if word in _BY_SPELLING:
            known.add(_BY_SPELLING[word])
        elif word not in unknown:
            unknown.append(word)
    return ordered(known), unknown


def from_texts(texts: list[str], instruction_ids: list[str]) -> set[str]:
    """The risks the words of the rules and scenario names, and the steps, of a task raise."""
    found = {r.name for r in RISKS if any(r.words.search(t) for t in texts)}
    return found | {r.name for r in RISKS if r.steps and any(i.startswith(r.steps) for i in instruction_ids)}


_CONFLICT = _words("concurren*", "conflict*", "race*", "same time", "twice", "lost update*", "lock*")
_RETRY = _words("retry", "retries", "retried", "idempoten*", "duplicate*", "again", "timeout*", "time out")


def from_design(tables: dict, server: bool, block_kinds: list[str]) -> set[str]:
    """The risks the technical design raises for a task: its Security, Errors and Data rows when the task has server-side
    code (``server``), and the date and time zone building blocks of the task."""
    from . import designsections
    normal = designsections.normal
    found: set[str] = set()
    if server:
        for row in tables["Security and privacy"].rows:
            kind = normal(row.get("Kind"))
            if kind == "rate limit":
                found.add("rate limits")
            elif kind.startswith("authori"):
                found.add("authorisation")
            elif kind == "personal data":
                found.add("personal data")
        for row in tables["Errors and resilience"].rows:
            text = " ".join(row.cells.values())
            found |= {"concurrent writes"} if _CONFLICT.search(text) else set()
            found |= {"retries and idempotency"} if _RETRY.search(text) else set()
        for row in tables["Data and performance"].rows:
            kind = normal(row.get("Kind"))
            if kind in ("table", "migration"):
                found.add("unmapped storage errors")
            elif kind in ("query", "volume"):
                found.add("large lists")
    if any(kind in ("date", "time zone") for kind in block_kinds):
        found.add("time zones")
    return found


_ANSWER = re.compile(r"^[ \t]*(?:[-*+][ \t]+)?\**Risk[ \t]+(?P<name>[^:\s][^:\n]*):(?P<answer>[^\n]*)$",
                     re.IGNORECASE | re.MULTILINE)
_HANDLED = re.compile(r"handled in (?P<path>[^\s:]+):(?P<line>\d+)\b", re.IGNORECASE)
_NOT_APPLICABLE = re.compile(r"not applicable\s*:\s*(?P<reason>.*)", re.IGNORECASE)


def answers(text: str) -> dict[str, str]:
    """{risk: the answer} for the first ``Risk <name>:`` line of each known risk in a report."""
    found: dict[str, str] = {}
    for match in _ANSWER.finditer(text):
        name = _BY_SPELLING.get(" ".join(match.group("name").strip(" *_`").casefold().split()))
        if name and name not in found:
            found[name] = match.group("answer").strip().strip("*_` ")
    return found


# A path relative to the project, with forward slashes: no drive, root, backslash, percent sign or control character.
_PROJECT_PATH = re.compile(r"[\w.@+-]+(?:/[\w.@+-]+){0,30}")


def _place_problem(root: Path, path: str, line: int) -> str | None:
    """Why ``path:line`` is not a line of a file of the project, or None."""
    from .issues import safe_cell
    count = 0
    if _PROJECT_PATH.fullmatch(path) and ".." not in path.split("/"):     # judged on the text before any file is touched
        try:
            target = root / path
            count = len(target.read_text(encoding="utf-8", errors="replace").splitlines()) if target.is_file() else 0
        except (OSError, ValueError):
            count = 0
    if count == 0:
        return f"{safe_cell(path)} is not a file of the project"
    return None if 1 <= line <= count else f"{safe_cell(path)} has no line {line}"


def review_problems(rel: str, text: str, risks: list[str], root: Path | None = None) -> list[str]:
    """Why a code review does not answer the risks of its task: a risk with no line, one marked missing, an answer that is
    neither a place in the code nor a reason it does not apply, or (with ``root``) a place that is not a line of a file."""
    given = answers(text)
    problems = []
    for risk in risks:
        answer = given.get(risk)
        reason = _NOT_APPLICABLE.match(answer or "")
        handled = _HANDLED.match(answer or "")
        place = _place_problem(root, handled.group("path"), int(handled.group("line"))) if handled and root else None
        if place:
            problems.append(f'{rel}: the line for the risk "{risk}" names a place that does not exist: {place}')
        elif answer is None:
            problems.append(f'{rel} has no line for the risk "{risk}": the code-reviewer writes "Risk {risk}: handled in '
                            'FILE:LINE", "not applicable: REASON" or "missing"')
        elif answer.casefold().startswith("missing"):
            problems.append(f'{rel} says the risk "{risk}" is missing: the writer handles it, then the code-reviewer runs again')
        elif not (handled or (reason and len(reason.group("reason").strip()) >= MIN_REASON)):
            problems.append(f'{rel}: the line for the risk "{risk}" names neither a place (handled in FILE:LINE) nor a reason '
                            "it does not apply (not applicable: REASON)")
    return problems
