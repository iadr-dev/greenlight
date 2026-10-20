"""Reading JUnit XML, the one result format every runner can write.

The file is produced by a test run on the person's machine, but a test (or the code under test) can
write anything, so a document type declaration or entity is refused instead of expanded.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .errors import UsageError

PASSED, FAILED, ERRORED, SKIPPED = "passed", "failed", "error", "skipped"
_FORBIDDEN = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


@dataclass(frozen=True)
class Case:
    name: str
    classname: str
    outcome: str          # passed | failed | error | skipped
    text: str             # failure or error message plus body, or the skip reason; empty for a pass

    @property
    def label(self) -> str:
        return f"{self.classname}::{self.name}" if self.classname else self.name


def parse_file(path: Path) -> list[Case]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise UsageError(f"cannot read the test report {path}: {exc}") from exc
    return parse(data, str(path))


def parse(data: bytes, where: str = "<report>") -> list[Case]:
    if _FORBIDDEN.search(data):
        raise UsageError(f"{where}: a test report with a DOCTYPE or ENTITY declaration is refused")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise UsageError(f"{where} is not valid JUnit XML: {exc}") from exc
    return [case_of(element) for element in root.iter("testcase")]


_OUTCOME_OF_TAG = {"failure": FAILED, "error": ERRORED, "skipped": SKIPPED}


def case_of(element: ET.Element) -> Case:
    outcome, text = PASSED, ""
    for child in element:
        if child.tag in _OUTCOME_OF_TAG:
            outcome = _OUTCOME_OF_TAG[child.tag]
            text = "\n".join(part for part in (child.get("type"), child.get("message"), child.text) if part).strip()
            if outcome != SKIPPED:
                break                                 # a failure outranks a skip recorded on the same case
    return Case(element.get("name", ""), element.get("classname", ""), outcome, text)
