"""`bdd gallery`: the one page the person looks at to approve the product design.

    bdd gallery                      write <design folder>/gallery.html and list what the checks found
    bdd gallery --out FILE           write it elsewhere in the project
    bdd gallery --check              only check the design (exit 1 on findings); prints the design's digest

The page is self-contained: every screen file, the flows and their stylesheets are inlined, each in a sandboxed frame
that runs no script, and a content security policy refuses every network request, so opening it fetches nothing. It
shows the feature map with every inventory row as a card under its feature (its states, and whether its screen file
shows each), the flows, every screen file at a phone width and a desktop width with each state labelled, and the gaps
the checks found. It is written from the design and read by nobody else, so it is not part of what is approved.
"""
from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import os
import re
import sys
from pathlib import Path, PurePosixPath

from . import config as cfg
from . import designfolder, designstage, lockfile, store
from .errors import StoreError, UsageError

POLICY = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; frame-src 'self'"
FRAME_POLICY = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:"
WIDTHS = (375, 1280)
MAX_INLINE = 1_000_000
_SCRIPT = re.compile(r"<script\b[^>]*>.*?</script\s*>|<script\b[^>]*/?>", re.IGNORECASE | re.DOTALL)
_STYLESHEET = re.compile(r"<link\b[^>]*>", re.IGNORECASE)
_HREF = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
_SRC = re.compile(r"""(<img\b[^>]*?\bsrc\s*=\s*)(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
_URL = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.IGNORECASE)
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)
_HEAD = re.compile(r"<head\b[^>]*>", re.IGNORECASE)
_ON_ATTRIBUTE = re.compile(r"""\son[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)
LABELS = ("[data-state]{outline:2px dashed #8a8f98;outline-offset:4px;margin:28px 8px 12px}"
          "[data-state]::before{content:attr(data-screen) ' \\00b7  ' attr(data-state);display:block;"
          "font:600 12px/1.6 system-ui,sans-serif;color:#4a4f57;margin:-24px 0 6px}")
STYLE = """
body{margin:0;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:#1d2126;background:#f6f7f9}
header,main{max-width:1400px;margin:0 auto;padding:16px 24px}
header{border-bottom:1px solid #dfe2e6;background:#fff;max-width:none}
h1{font-size:24px;margin:8px 0}h2{font-size:20px;margin:32px 0 8px}h3{font-size:16px;margin:0 0 4px}
nav a{margin-right:12px}a{color:#0b57d0}
.findings li{color:#8a1c12}.ok{color:#145c32}.gap{color:#8a1c12;font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.card{background:#fff;border:1px solid #dfe2e6;border-radius:8px;padding:12px}
.card p{margin:2px 0;color:#4a4f57;font-size:13px}.states{list-style:none;padding:0;margin:6px 0;display:flex;flex-wrap:wrap;gap:6px}
.states li{border:1px solid currentColor;border-radius:12px;padding:0 8px;font-size:12px}
.frames{display:flex;gap:16px;overflow-x:auto;align-items:flex-start;padding-bottom:8px}
.frame{flex:none}.frame p{margin:0 0 4px;font-size:12px;color:#4a4f57}
iframe{border:1px solid #c9cdd3;background:#fff;height:720px;display:block}
"""


def esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def anchor(rel: str) -> str:
    return "screen-" + re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-")


class Inliner:
    """Turns a file of the design folder into a document that needs nothing else: its stylesheets and images inlined,
    its scripts and event handlers removed. Reads only files inside the design folder."""

    def __init__(self, root: Path, folder: str):
        self.root, self.folder = root, folder

    def local(self, rel_dir: PurePosixPath, ref: str) -> Path | None:
        if not ref or _EXTERNAL.match(ref) or ref.startswith("#"):
            return None
        target = self.root / (rel_dir / ref.split("?")[0].split("#")[0]).as_posix()
        if target.is_file() and designfolder.inside(self.root, self.folder, target) and target.stat().st_size <= MAX_INLINE:
            return target
        return None

    def data_uri(self, path: Path) -> str:
        kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return f"data:{kind};base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    def css(self, text: str, rel_dir: PurePosixPath) -> str:
        def url(match: re.Match) -> str:
            target = self.local(rel_dir, match.group(2).strip())
            return f"url({self.data_uri(target)})" if target else "url()"
        return _URL.sub(url, text).replace("</style", "<\\/style")

    def document(self, rel: str) -> str:
        rel_dir = PurePosixPath(rel).parent
        text = (self.root / rel).read_text(encoding="utf-8-sig", errors="replace")
        text = _ON_ATTRIBUTE.sub("", _SCRIPT.sub("", text))

        def link(match: re.Match) -> str:
            tag = match.group(0)
            if "stylesheet" not in tag.casefold():
                return ""
            href = _HREF.search(tag)
            target = self.local(rel_dir, next((g for g in href.groups() if g is not None), "")) if href else None
            if target is None:
                return ""
            css_dir = PurePosixPath(target.relative_to(self.root).as_posix()).parent
            return f"<style>{self.css(target.read_text(encoding='utf-8-sig', errors='replace'), css_dir)}</style>"

        def image(match: re.Match) -> str:
            target = self.local(rel_dir, next(g for g in match.groups()[1:] if g is not None))
            return f'{match.group(1)}"{self.data_uri(target) if target else ""}"'

        text = _SRC.sub(image, _STYLESHEET.sub(link, text))
        text = re.sub(r"(<style\b[^>]*>)(.*?)(</style\s*>)", lambda m: m.group(1) + self.css(m.group(2), rel_dir) + m.group(3),
                      text, flags=re.IGNORECASE | re.DOTALL)
        head = f'<meta http-equiv="Content-Security-Policy" content="{FRAME_POLICY}"><style>{LABELS}</style>'
        found = _HEAD.search(text)
        return text[:found.end()] + head + text[found.end():] if found else f"<head>{head}</head>" + text


def frame(document: str, width: int, title: str) -> str:
    return (f'<div class="frame"><p>{width} px</p><iframe title="{esc(title)} at {width} px" sandbox width="{width}" '
            f'srcdoc="{esc(document)}"></iframe></div>')


def card(row: designfolder.Row, design: designfolder.Design, inventory: str, link_base: Path) -> str:
    rel = designfolder._normal((PurePosixPath(inventory).parent / row.file).as_posix()) if row.file else ""
    screen = design.screens.get(rel)
    states = "".join(
        f'<li class="{"ok" if screen and (row.id, designfolder.state_name(s)) in screen.shown else "gap"}">{esc(s)}</li>'
        for s in row.states)
    if screen:
        where = (f'<a href="{esc(os.path.relpath(design.root / rel, link_base).replace(os.sep, "/"))}">{esc(row.file)}</a> '
                 f'(<a href="#{anchor(rel)}">shown below</a>)')
    else:
        where = f'<span class="gap">{esc(row.file or "no screen file")}</span>'
    return (f'<article class="card" data-row="{esc(row.id)}"><h3>{esc(row.id)} {esc(row.screen)}</h3>'
            f'<p>{esc(row.section)}</p><ul class="states">{states}</ul><p>{where}</p></article>')


def build(root: Path, out: Path, design: designfolder.Design) -> str:
    files = designfolder.files_of(cfg.load(root), design.folder)
    inliner = Inliner(root, design.folder)
    title = product_name(root, files["product"])
    status = designstage.status_line(designstage.status(root))
    known = {f.id for f in design.features}
    parts = [f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
             f'<meta http-equiv="Content-Security-Policy" content="{POLICY}">'
             f'<meta name="viewport" content="width=device-width, initial-scale=1">'
             f"<title>{esc(title)}: design gallery</title><style>{STYLE}</style></head><body>",
             f"<header><h1>{esc(title)}: the design</h1><p>{esc(status)}</p><p>{esc(counts(design))}</p>"
             '<nav><a href="#features">Features</a><a href="#flows">Flows</a><a href="#screens">Screens</a>'
             '<a href="#findings">Findings</a></nav></header><main>']
    parts.append('<section id="findings"><h2>Findings</h2>' + (
        "<ul class=\"findings\">" + "".join(f"<li>{esc(i)}</li>" for i in design.issues) + "</ul>"
        if design.issues else '<p class="ok">The design checks found nothing.</p>') + "</section>")
    parts.append('<section id="features"><h2>Features and their screens</h2>')
    groups = [(f.id, f"{f.id} {f.name}", f"{f.description} Depends on: {', '.join(f.depends) or 'nothing'}. Order: {f.order}.")
              for f in design.features]
    if any(not set(r.features) & known for r in design.rows):
        groups.append(("other", "Not in the product map", "Rows whose feature the product map does not list."))
    for key, heading, about in groups:
        rows = [r for r in design.rows if (key in r.features if key != "other" else not set(r.features) & known)]
        parts.append(f'<h2 id="{esc(key)}">{esc(heading)}</h2><p>{esc(about)}</p><div class="cards">'
                     + "".join(card(r, design, files["inventory"], out.parent) for r in rows) + "</div>")
    parts.append("</section>")
    parts.append('<section id="flows"><h2>Flows</h2>')
    if (root / files["flows"]).is_file():
        parts.append('<div class="frames">' + frame(inliner.document(files["flows"]), WIDTHS[1], "Flows") + "</div>")
    else:
        parts.append(f'<p class="gap">{esc(files["flows"])} does not exist yet.</p>')
    parts.append('</section><section id="screens"><h2>Screens</h2>')
    for rel in design.screens:
        document = inliner.document(rel)
        link = os.path.relpath(root / rel, out.parent).replace(os.sep, "/")
        parts.append(f'<h3 id="{anchor(rel)}"><a href="{esc(link)}">{esc(rel)}</a></h3><div class="frames">'
                     + "".join(frame(document, width, rel) for width in WIDTHS) + "</div>")
    parts.append("</section></main></body></html>\n")
    return "".join(parts)


def counts(design: designfolder.Design) -> str:
    states = sum(len(r.states) for r in design.rows)
    return f"{len(design.rows)} screens, {states} states, {len(design.features)} features"


def product_name(root: Path, rel: str) -> str:
    path = root / rel
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    return designstage.NAME


def output_path(root: Path, folder: str, out: str | None) -> Path:
    default = root / folder / designfolder.GALLERY
    if out is None:
        return default
    target = (Path(out) if Path(out).is_absolute() else Path.cwd() / out).resolve()
    rel = lockfile.relative(root, target)
    if designfolder.covers(folder, rel) or rel.split("/")[0] == cfg.BDD_DIR:
        raise UsageError(f"--out {out}: the gallery is written outside the design and .bdd/, or as "
                         f"{folder}/{designfolder.GALLERY}")
    return target


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="bdd gallery", description="Build the one page the person approves the design from.")
    ap.add_argument("--out", help="where to write the page (default: gallery.html in the design folder)")
    ap.add_argument("--check", action="store_true", help="only check the design and print its digest; write nothing")
    args = ap.parse_args(argv)
    try:
        from .statecmd import project_root
        root = project_root().resolve()
        design = designfolder.load(root)
        if not (root / design.folder).is_dir():
            raise UsageError(f"there is no design folder ({design.folder}/); the design stage writes it")
        findings = [str(issue) for issue in design.issues]
        if args.check:
            print("\n".join(findings) if findings else "the design checks found nothing")
            print(f"design digest: {designstage.digest_of(designstage.current_files(root, design.folder))}")
            return 1 if findings else 0
        out = output_path(root, design.folder, args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(out, build(root, out, design))
    except (UsageError, StoreError, cfg.ConfigError, OSError) as exc:
        print(f"bdd gallery: {exc}", file=sys.stderr)
        return 2
    print(f"{lockfile.relative(root, out)}: {counts(design)}")
    if findings:
        print("\n".join(findings))
        print(f"{len(findings)} finding(s); the page lists them too")
    return 1 if findings else 0

