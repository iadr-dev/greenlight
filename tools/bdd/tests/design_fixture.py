"""A small, complete product design in a throwaway project, in the shape the design stage writes."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bddlib import claudepaths, designstage, enforcement, gallery

CONFIG = ('[[adapters]]\nname = "x"\nfeatures = "features"\nsteps = "steps"\n\n'
          '[design]\nsystem = "design/DESIGN.md"\nscreens = "design/screens/*"\ninventory = "design/inventory.md"\n')
PRODUCT = "# Shop\n\n## Users\nShoppers.\n\n## Jobs\nPlace an order.\n\n## Platforms\nweb\n"
MAP = ("# Product map\n\n| ID | Feature | Description | Depends on | Order |\n|---|---|---|---|---|\n"
       "| FEAT-001 | Sign in | A shopper signs in. | - | 1 |\n"
       "| FEAT-002 | Orders | A shopper places an order. | FEAT-001 | 2 |\n")
SECTIONS = {"Stack per surface": "| Surface | Stack |\n|---|---|\n| web | Next.js |", "Layers": "Pages, services, data.",
            "Hosting and environments": "Vercel.", "Authentication": "Magic link.", "Data store": "Postgres.",
            "Security baseline and threat model": "| Threat | Control |\n|---|---|\n| Stolen session | Secure cookie |",
            "Observability": "Logs.", "CI and delivery": "Tests on every pull request."}
ARCHITECTURE = "# Architecture\n\n" + "".join(f"## {name}\n{body}\n\n" for name, body in SECTIONS.items())
INVENTORY = ("# Screen inventory\n\n## Sign in and orders\n\n| ID | Screen | States | Feature | File |\n|---|---|---|---|---|\n"
             "| S-IN-01 | Sign in | loading, error, success | FEAT-001 | screens/home.html |\n"
             "| S-OR-01 | Order list | loading, empty, error, success | FEAT-002 | screens/home.html |\n")
STATES = {"S-IN-01": ("loading", "error", "success"), "S-OR-01": ("loading", "empty", "error", "success")}


def screen(states: dict[str, tuple[str, ...]] = STATES, head: str = '<link rel="stylesheet" href="../tokens.css">') -> str:
    sections = "".join(f'<section data-screen="{row}" data-state="{state}"><h2>{row} {state}</h2></section>\n'
                       for row, names in states.items() for state in names)
    return f"<!doctype html>\n<html><head>{head}</head><body>\n{sections}</body></html>\n"


class DesignCase(unittest.TestCase):
    """A project whose design stage is started and whose design passes every check."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name).resolve()
        self.transcripts = self.root / "transcripts" / "projects"
        self.transcripts.mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {claudepaths.TRANSCRIPT_ROOT_ENV: str(self.transcripts)})
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(enforcement.SESSION_ENV, None)
        cwd = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, cwd)
        self.write(".bdd/config.toml", CONFIG)
        self.write("product-spec.md", "A small shop.\n")
        self.write("design/PRODUCT.md", PRODUCT)
        self.write(".bdd/product.md", MAP)
        self.write(".bdd/architecture.md", ARCHITECTURE)
        self.write("design/DESIGN.md", "# Shop design\n\n## Design contract\nThe order list first.\n")
        self.write("design/tokens.json", '{"color": {"primary": "#137547"}}\n')
        self.write("design/tokens.css", ":root { --primary: #137547; }\n")
        self.write("design/flows.html", "<!doctype html><html><body><ol><li>S-IN-01</li><li>S-OR-01</li></ol></body></html>\n")
        self.write("design/inventory.md", INVENTORY)
        self.write("design/screens/home.html", screen())

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def start(self) -> None:
        designstage.start(self.root, self.root / "product-spec.md")

    def review(self, verdict: str = "PASS") -> None:
        """The ui-reviewer's report on the design as it is now, then the gallery built from it."""
        digest = designstage.digest_of(designstage.current_files(self.root, "design"))
        self.write(designstage.REVIEW, f"# Design review\n\nDesign: {digest}\nVerdict: {verdict}\n")
        self.build()

    def build(self) -> None:
        out = self.root / "design" / "gallery.html"
        from bddlib import designfolder, store
        store.write_text(out, gallery.build(self.root, designfolder.load(self.root)))

    def ready(self) -> None:
        self.start()
        self.review()

    def transcript(self, *entries: dict, name: str = "session.jsonl") -> Path:
        import json
        path = self.transcripts / name
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        return path
