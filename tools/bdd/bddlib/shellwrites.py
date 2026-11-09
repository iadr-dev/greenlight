"""Where a shell command writes, read off the command the way a shell reads it.

The guard used to count a command as a write when a write word appeared anywhere in it (``Move`` in a quoted argument, a
``>`` inside a regular expression), and as a write to a protected file when that file's name appeared anywhere in it.
This reads the command into words, quotes, here-documents, separators, redirections and changes of folder, and returns
what it writes to: the targets of its output redirections, the arguments of the commands that change files, and the
code of an interpreter whose code writes, with the folders a relative path in each may land in. The guard checks its
protections against those alone.

It reads, it does not run. Whatever it cannot read off the command makes the whole command the target, which is what
the guard did before: an unbalanced quote or an unterminated here-document, a variable it cannot pin to one value in a
word that is written or in the program word, a program the shell picks by a glob, a program whose files come from its
input (``xargs rm``, ``... | sh``), a here-document that runs a command substitution.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

WRITE_VERBS = {"tee", "cp", "mv", "rm", "truncate", "dd", "install", "ln", "chmod", "touch", "set-content", "add-content",
               "out-file", "remove-item", "move-item", "copy-item", "new-item", "del", "erase", "move", "copy"}
COPY_VERBS = {"cp", "mv", "ln", "install", "copy", "copy-item", "move", "move-item"}   # they write into a folder too
GIT_WRITES = {"checkout", "restore", "reset", "stash", "apply", "rm", "mv", "clean"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "cmd", "powershell", "pwsh", "eval", "source", ".", "su", "ssh",
          "watch", "script"}
INTERPRETERS = {"python", "pythonw", "py", "node", "nodejs", "bun", "deno", "perl", "ruby", "php", "awk", "gawk", "tsx",
                "lua", "luajit", "rscript", "julia", "tclsh", "groovy", "jshell"}
RUNNERS = {"xargs", "parallel"}                         # they run a program on the names they read
VERSION_ONLY = {"--version", "-v", "-V", "--help", "-h"}  # `node --version` runs no code
MOVES = {"cd", "pushd", "chdir", "set-location", "sl", "push-location"}
RUNS = WRITE_VERBS | SHELLS | INTERPRETERS | RUNNERS | {"git", "sed", "perl", "find"}   # a quoted argument starting so is read
READS_INTO = {"read", "mapfile", "readarray", "getopts"}  # they assign variables the guard cannot know
FIND_ACTIONS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
FOLDER_FLAGS = ("--directory", "--chdir", "--git-dir", "--work-tree", "--prefix", "--cwd", "--dir")
# The flags with which `cp` writes only its destination (a folder target, a link or a hard link writes elsewhere too).
CP_SAFE_SHORT = set("aRrfpvniuPLdHx")
CP_SAFE_LONG = ("--recursive", "--force", "--preserve", "--no-preserve", "--verbose", "--no-clobber", "--interactive",
                "--update", "--archive", "--dereference", "--no-dereference", "--parents")
HARMLESS_TARGETS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "nul", "con"}
GROUPING = {"{", "}", "!", "(", ")"}
# What makes interpreter code a write: Python, Node, Perl, Ruby, PHP, Lua spellings, code that runs a shell, and code that
# calls by a computed name (then any name in it counts).
CODE_WRITES = re.compile(
    r"write_text|write_bytes|(?<!stdout)(?<!stderr)(?<!buffer)\.write\(|\.writelines\(|:write\("
    r"|open\((?:[^()]|\([^()]*\))*?[\"'][rwabxt+]*[wax+][rwabxt+]*[\"']"
    r"|\bos\.(?:remove|rename|replace|unlink|rmdir|removedirs|truncate|symlink|link|chmod|makedirs|mkdir)\b|\bshutil\."
    r"|\.(?:unlink|rename|rmdir|touch|symlink_to|hardlink_to|chmod|mkdir)\("
    r"|\bfs(?:\.promises|p)?\.(?!(?:read|exists|stat|lstat|access|realpath|opendir|watch|constants)\w*)\w+"
    r"|\b(?:writeFile|appendFile|createWriteStream|copyFile|renameSync|unlinkSync|rmSync|rmdirSync|truncateSync|"
    r"symlinkSync|chmodSync|mkdirSync)\w*\s*\("
    r"|\bunlink\b|\bFile\.(?:write|open|delete|rename|unlink|binwrite)|\bfile_put_contents\b|\bfopen\s*\("
    r"|\bopen\s*\(?\s*(?:my\s+)?\$?\w+\s*,\s*[\"']?\s*[>+]"
    r"|subprocess|\bos\.(?:system|popen|exec\w*|spawn\w*)|\bPopen\b|child_process|\bexec\w*\b|\bspawn\w*\b|\bsystem\b"
    r"|\bqx\b|%x|\bio\.popen\b|\bgetattr\b|__import__|\bimportlib\b|\beval\b|\bcompile\s*\(")
SHELL_QUOTES = re.compile(r"`")                         # Perl, Ruby and PHP run a backtick string as a command
AWK_WRITES = re.compile(r"\bprintf?\b[^;}\n]*>|\bsystem\s*\(|\|\s*\"")       # awk: `print > "file"`, `system(...)`, a pipe
_VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+)|(\{[^}]*\}|[@*#?$!\-]))")
_ASSIGNMENT = re.compile(r"([A-Za-z_]\w*)(\+?)=")
_SUFFIX = re.compile(r"\.(?:exe|cmd|bat|ps1)$")
_VERSION = re.compile(r"(?<=[a-z])[\d.]+$")
MAX_DEPTH = 4


class Unreadable(Exception):
    """The command cannot be read reliably enough to say where it writes."""


@dataclass
class Word:
    """A shell word: its parts with how each was quoted (``plain``, ``double``, ``single`` or ``ansi``)."""
    parts: list[tuple[str, str]] = field(default_factory=list)
    substitutions: list[str] = field(default_factory=list)    # the commands of its command substitutions
    windows: str = ""                          # the word read with each backslash as a folder separator

    def add(self, text: str, how: str, windows: str | None = None) -> None:
        if self.parts and self.parts[-1][1] == how:
            self.parts[-1] = (self.parts[-1][0] + text, how)
        else:
            self.parts.append((text, how))
        self.windows += text if windows is None else windows

    @property
    def text(self) -> str:
        return "".join(text for text, _ in self.parts)

    @property
    def quoted(self) -> bool:
        return bool(self.parts) and all(how != "plain" for _, how in self.parts)

    @property
    def partly_quoted(self) -> bool:
        return any(how != "plain" for _, how in self.parts)

    def name(self) -> str:
        """The program this word names, if it is one: its last path segment, case-folded, without an extension that
        only says how it runs or a version number (``python3.12`` is ``python``)."""
        if self.quoted and not self.text:
            return ""
        return program_name(self.text)


def program_name(text: str) -> str:
    segment = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].strip("{}()").casefold()
    return _VERSION.sub("", _SUFFIX.sub("", segment))


@dataclass
class Simple:
    words: list[Word] = field(default_factory=list)
    redirects: list[Word] = field(default_factory=list)    # where its output goes
    bodies: list[str] = field(default_factory=list)        # its here-documents and here-strings
    expands: bool = False                                  # a here-document body runs a command substitution
    joiner: str = ""                                       # the operator after it
    nested: list["Simple"] = field(default_factory=list)   # the commands of its command substitutions


@dataclass
class Target:
    """One place the command writes: a word (``code`` False) or the code of an interpreter (``code`` True)."""
    text: str
    raw: str
    pattern: str
    dirs: tuple[Path | None, ...]
    code: bool = False
    names_only: bool = False                               # its paths are names (a find pattern, a -C folder)
    certain: bool = False                                  # every folder in ``dirs`` came from a `cd` to a known place
    source: str = ""                                       # the word as written, variables not put in


@dataclass
class Writes:
    targets: list[Target] = field(default_factory=list)
    context: list[str] = field(default_factory=list)       # the folders the command moves into, as written
    whole: bool = False                                    # check the whole command: the targets are not known
    made: set[Path] = field(default_factory=set)           # the folders a `mkdir` in the command creates


# -- reading the command ------------------------------------------------------------------------------------------
class _Lexer:
    def __init__(self, text: str, depth: int):
        self.text, self.at, self.depth = text, 0, depth
        self.commands: list[Simple] = []
        self.current = Simple()
        self.word: Word | None = None
        self.heredocs: list[tuple[str, bool, Simple, bool]] = []
        self.next_is: str | None = None                   # "target", "delimiter", "string", "drop"
        self._strip_tabs = False

    def run(self) -> list[Simple]:
        while self.at < len(self.text):
            self.step()
        self.end_word()
        if self.heredocs or self.next_is in ("delimiter", "string"):
            raise Unreadable("a here-document is not terminated")
        self.end_command("")
        return self.commands

    def peek(self, offset: int = 0) -> str:
        at = self.at + offset
        return self.text[at] if at < len(self.text) else ""

    def ensure_word(self) -> Word:
        if self.word is None:
            self.word = Word()
        return self.word

    def end_word(self) -> None:
        word, self.word = self.word, None
        if word is None:
            return
        role, self.next_is = self.next_is, None
        if role == "target":
            self.current.redirects.append(word)
        elif role == "delimiter":
            self.heredocs.append((word.text, self._strip_tabs, self.current, not word.partly_quoted))
        elif role == "string":
            self.current.bodies.append(word.text)
        elif role is None:
            self.current.words.append(word)

    def end_command(self, joiner: str) -> None:
        self.end_word()
        if self.next_is is not None:
            raise Unreadable("a redirection has no target")
        if self.current.words or self.current.redirects or self.current.bodies or self.current.nested:
            self.current.joiner = joiner
            self.commands.append(self.current)
        self.current = Simple()

    def step(self) -> None:
        char = self.peek()
        if char in " \t\r":
            self.end_word()
            self.at += 1
        elif char == "\n":
            self.end_command("\n")
            self.at += 1
            self.read_heredocs()
        elif char == "#" and self.word is None:
            while self.at < len(self.text) and self.text[self.at] != "\n":
                self.at += 1
        elif char == "\\":
            if self.peek(1) == "\n":
                self.at += 2
            else:
                self.ensure_word().add(self.peek(1), "single", "\\" + self.peek(1))
                self.at += 2
        elif char == "'":
            end = self.text.find("'", self.at + 1)
            if end < 0:
                raise Unreadable("a single quote is not closed")
            self.ensure_word().add(self.text[self.at + 1:end], "single")
            self.at = end + 1
        elif char == '"':
            self.read_double()
        elif char == "$" and self.peek(1) == "'":
            self.read_ansi()
        elif char == "$" and self.peek(1) == "(":
            self.read_substitution(2)
        elif char in "<>" and self.peek(1) == "(":
            self.read_substitution(2)                          # `<(cmd)`, `>(cmd)`: a process substitution
        elif char == "`":
            self.read_backticks()
        elif char in ";&|()":
            self.read_operator()
        elif char in "<>":
            self.read_redirect()
        else:
            self.ensure_word().add(char, "plain")
            self.at += 1

    def read_double(self) -> None:
        word, at, chunk = self.ensure_word(), self.at + 1, []
        while True:
            if at >= len(self.text):
                raise Unreadable("a double quote is not closed")
            char = self.text[at]
            if char == '"':
                break
            if char == "\\" and at + 1 < len(self.text) and self.text[at + 1] in '"\\$`\n':
                chunk.append(self.text[at + 1] if self.text[at + 1] != "\n" else "")
                at += 2
                continue
            if char == "`" or (char == "$" and at + 1 < len(self.text) and self.text[at + 1] == "("):
                word.add("".join(chunk), "double")
                chunk = []
                self.at = at
                if char == "`":
                    self.read_backticks()
                else:
                    self.read_substitution(2)
                at = self.at
                continue
            chunk.append(char)
            at += 1
        word.add("".join(chunk), "double")
        self.at = at + 1

    def read_ansi(self) -> None:
        at, chunk = self.at + 2, []
        while True:
            if at >= len(self.text):
                raise Unreadable("an ANSI-C quote is not closed")
            if self.text[at] == "\\" and at + 1 < len(self.text):
                chunk.append(self.text[at:at + 2])
                at += 2
                continue
            if self.text[at] == "'":
                break
            chunk.append(self.text[at])
            at += 1
        try:
            decoded = "".join(chunk).encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            decoded = "".join(chunk)
        self.ensure_word().add(decoded, "ansi")
        self.at = at + 1

    def read_substitution(self, skip: int) -> None:
        """``$( ... )``: find the matching parenthesis (quotes inside respected) and read what is inside as commands."""
        depth, at, quote = 1, self.at + skip, ""
        while at < len(self.text):
            char = self.text[at]
            if quote:
                if char == "\\" and quote == '"':
                    at += 2
                    continue
                if char == quote:
                    quote = ""
            elif char in "'\"":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            at += 1
        if depth:
            raise Unreadable("a command substitution is not closed")
        self.nest(self.text[self.at + skip:at])
        self.at = at + 1

    def read_backticks(self) -> None:
        end = self.at + 1
        while end < len(self.text) and self.text[end] != "`":
            end += 2 if self.text[end] == "\\" else 1
        if end >= len(self.text):
            raise Unreadable("a backtick substitution is not closed")
        self.nest(self.text[self.at + 1:end])
        self.at = end + 1

    def nest(self, inner: str) -> None:
        if self.depth >= MAX_DEPTH:
            raise Unreadable("command substitutions are nested too deeply")
        self.current.nested += _Lexer(inner, self.depth + 1).run()
        word = self.ensure_word()
        word.substitutions.append(inner)
        word.add("$(...)", "double")

    def read_operator(self) -> None:
        two = self.text[self.at:self.at + 2]
        if two in ("&&", "||", "|&", ";;"):
            self.end_command(two)
            self.at += 2
        elif self.peek() == "&" and self.peek(1) == ">":
            self.read_redirect()
        else:
            self.end_command(self.peek())
            self.at += 1

    def read_redirect(self) -> None:
        fd = self.word is not None and self.word.text.isdigit() and not self.word.quoted
        if fd:
            self.word = None                                    # `2>`: the number names the stream, it is no word
        else:
            self.end_word()
        if self.next_is is not None:
            raise Unreadable("a redirection has no target")
        for op in ("&>>", "<<<", "<<-", ">>", "&>", ">|", ">&", "<&", "<>", "<<", ">", "<"):
            if self.text.startswith(op, self.at):
                break
        self.at += len(op)
        while self.peek() and self.peek() in " \t":
            self.at += 1
        if op in (">&", "<&") and (self.peek().isdigit() or self.peek() == "-"):
            while self.peek() and (self.peek().isdigit() or self.peek() == "-"):
                self.at += 1
            return
        self._strip_tabs = op == "<<-"
        self.next_is = {"<<": "delimiter", "<<-": "delimiter", "<<<": "string", "<": "drop", "<&": "drop"}.get(op, "target")

    def read_heredocs(self) -> None:
        for delimiter, strip, owner, expands in self.heredocs:
            lines = []
            while True:
                if self.at >= len(self.text):
                    raise Unreadable("a here-document is not terminated")
                end = self.text.find("\n", self.at)
                line = self.text[self.at:] if end < 0 else self.text[self.at:end]
                self.at = len(self.text) if end < 0 else end + 1
                if (line.lstrip("\t") if strip else line).rstrip("\r") == delimiter:
                    break
                lines.append(line)
            owner.bodies.append("\n".join(lines))
            owner.expands = owner.expands or (expands and any("$(" in line or "`" in line for line in lines))
        self.heredocs = []


def lex(command: str, depth: int = 0) -> list[Simple]:
    return _Lexer(command, depth).run()


def _all_simple(commands: list[Simple]):
    for simple in commands:
        yield from _all_simple(simple.nested)
        yield simple


# -- what the commands write ------------------------------------------------------------------------------------------
class _Unknown(Exception):
    """A word holds a value that cannot be known here."""


SCRATCH = "greenlight-scratch"


def _expand(word: Word, assigned: dict[str, str | None], strict: bool) -> tuple[str, str, str]:
    """The word's text with variables put in (local assignments first, then the environment), ``~`` as the home folder;
    its Windows reading (backslashes as separators); and its glob pattern (quoted glob characters made inert).
    ``strict``: raise ``_Unknown`` for a variable that is not known or a command substitution."""
    if word.substitutions and strict:
        raise _Unknown()
    text, pattern = [], []
    for index, (part, how) in enumerate(word.parts):
        value = part
        if how in ("plain", "double"):
            value = _CMD_VARIABLE.sub(_cmd_lookup, _VARIABLE.sub(lambda m: _lookup(m, assigned, strict), part))
            if how == "plain" and index == 0 and (value == "~" or value.startswith(("~/", "~\\"))):
                value = _home() + value[1:]
        text.append(value)
        pattern.append(value if how == "plain" else re.sub(r"[*?\[\]]", "\x00", value))
    raw = _CMD_VARIABLE.sub(_cmd_lookup, _VARIABLE.sub(lambda m: _lookup(m, assigned, False), word.windows))
    if raw == "~" or raw.startswith(("~/", "~\\")):
        raw = _home() + raw[1:]
    return "".join(text), raw.replace("\\", "/"), "".join(pattern)


def _home() -> str:
    return str(Path.home()).replace("\\", "/")


_CMD_VARIABLE = re.compile(r"%(\w+)%")
UNKNOWN_HERE = {"PWD", "OLDPWD"}                      # the shell's own folder, not the hook's


def _cmd_lookup(match: re.Match) -> str:
    """``%NAME%``, as cmd and PowerShell scripts spell a variable."""
    return os.environ.get(match.group(1), match.group(0))


def _lookup(match: re.Match, assigned: dict[str, str | None], strict: bool) -> str:
    name = match.group(1) or match.group(2)
    if name and name in assigned and assigned[name] is not None:
        return assigned[name]
    if name and name not in assigned and name not in UNKNOWN_HERE and os.environ.get(name) is not None:
        return os.environ[name]
    if strict:
        raise _Unknown()
    return match.group(0)


def _assignment(word: Word) -> tuple[str, Word] | None:
    """``NAME=value`` (or ``NAME+=value``) as a word: the name and the value as a word of its own."""
    if not word.parts or word.parts[0][1] != "plain":
        return None
    match = _ASSIGNMENT.match(word.parts[0][0])
    if not match:
        return None
    value = Word([(word.parts[0][0][match.end():], "plain"), *word.parts[1:]], word.substitutions,
                 word.windows[match.end():])
    return match.group(1), value


def _flag(word: Word) -> bool:
    return not word.quoted and word.text.startswith("-")


PREFIXES = {"env", "sudo", "doas", "command", "builtin", "exec", "nohup", "time", "nice", "ionice", "timeout", "stdbuf",
            "do", "then", "else", "elif", "if", "while", "until", "busybox"}
DECLARATIONS = {"export", "local", "declare", "readonly", "typeset"}


def _program_at(words: list[Word]) -> int:
    """Where the program word is: after the prefixes (``sudo``, ``timeout 20``, ``do``, ``{``) and the assignments and
    flags that belong to them."""
    at = 0
    while at < len(words):
        word = words[at]
        if not word.quoted and (word.text in GROUPING or word.name() in PREFIXES):
            at += 1
            while at < len(words) and (_flag(words[at]) or words[at].text.isdigit() or _assignment(words[at])):
                at += 1
            continue
        return at
    return at


def _stable(commands: list[Simple]) -> set[str]:
    """The variables the command assigns exactly once, by a plain ``NAME=value`` command of its own or a ``for`` list:
    one value is known for them. A variable assigned twice, by ``+=``, before a program (``NAME=x cmd``), after ``then`` or
    ``do``, in a declaration, or by ``read``, ``mapfile``, ``printf -v`` or ``getopts`` may hold another value, so it is
    not known."""
    counts: dict[str, int] = {}
    unknown: set[str] = set()
    for simple in _all_simple(commands):
        words = simple.words
        plain = bool(words) and all(_assignment(w) for w in words)
        for at, word in enumerate(words):
            found = _assignment(word) if not word.quoted else None
            if found:
                counts[found[0]] = counts.get(found[0], 0) + 1
                if not plain or re.match(r"[A-Za-z_]\w*\+=", word.parts[0][0]):
                    unknown.add(found[0])
        names = [w.name() for w in words]
        if names and names[0] == "for" and len(words) > 1:
            counts[words[1].text] = counts.get(words[1].text, 0) + 1
        start = _program_at(words)
        program = names[start] if start < len(names) else ""
        if program in READS_INTO:
            unknown |= {w.text for w in words[start + 1:] if not _flag(w)}
        if program == "printf" and any(w.text == "-v" for w in words):
            unknown |= {w.text for w in words if w.text not in ("-v", "printf")}
        if program in DECLARATIONS:
            unknown |= {found[0] for w in words if (found := _assignment(w))}
    return {name for name, count in counts.items() if count == 1 and name not in unknown}


class _Reader:
    def __init__(self, cwd: Path | None, stable: set[str]):
        self.assigned: dict[str, str | None] = {}
        self.stable = stable
        self.union: list[Path | None] = [cwd]           # every folder the command may be in by now
        self.chain: list[Path | None] | None = None      # the folders after a `cd ... &&`, for the rest of that chain
        self.dirs = self.union
        self.found = Writes()
        self.scripts: dict[str, str] = {}                # the scripts the command writes, by file name
        self.moves_codex = False                         # it sets CODEX_HOME
        self.exact: set[Path] = set()                    # folders a `cd` reached for sure (from an absolute path)
        self.after = ""                                  # the operator before the command being read

    def read(self, commands: list[Simple], depth: int) -> None:
        piped = chained = False
        self.after = ""
        for simple in commands:
            if not chained:
                self.chain = None
            chain = self.chain
            self.dirs = chain if chain is not None else self.union
            after = self.after
            self.read(simple.nested, depth)
            self.chain, self.after = chain, after
            self.dirs = chain if chain is not None else self.union
            self.read_simple(simple, piped, depth)
            piped, chained = simple.joiner in ("|", "|&"), simple.joiner == "&&"
            self.after = simple.joiner

    def target(self, word: Word, names_only: bool = False) -> None:
        try:
            text, raw, pattern = _expand(word, self.assigned, strict=True)
        except _Unknown:
            self.found.whole = True
            return
        if text.casefold() in HARMLESS_TARGETS or not text:
            return
        certain = bool(self.dirs) and all(folder in self.exact for folder in self.dirs)
        self.found.targets.append(Target(text, raw, pattern, tuple(self.dirs), names_only=names_only, certain=certain,
                                         source=word.text))

    def remember_script(self, simple: Simple, words: list[Word]) -> None:
        """A file the command writes may be run by it next: its here-document, or what ``echo`` or ``printf`` print."""
        data = "\n".join(simple.bodies)
        if not data and words and words[0].name() in ("echo", "printf"):
            data = " ".join(_expand(w, self.assigned, strict=False)[0] for w in words[1:])
        for word in simple.redirects:
            if data:
                self.scripts[_basename(word.text)] = data

    def read_simple(self, simple: Simple, piped: bool, depth: int) -> None:
        if simple.expands:
            self.found.whole = True                                # `<<EOF` with `$(...)` in it runs that command
            return
        for word in simple.redirects:
            self.target(word)
        words = list(simple.words)
        if words and words[0].name() == "for" and not words[0].quoted:
            self.loop(words[1:])
            return
        if words and all(_assignment(w) for w in words):
            for word in words:
                self.assign(*_assignment(word))
            return
        start = _program_at(words)
        while start < len(words) and _assignment(words[start]):
            self.moves_codex = self.moves_codex or _assignment(words[start])[0].upper() == "CODEX_HOME"
            start += 1                                         # `FOO=1 cmd`: for that command only
        words = words[start:]
        self.remember_script(simple, words)
        if not words:
            return
        program = words[0].name() if not words[0].quoted or words[0].text else ""
        if program in DECLARATIONS:
            for word in words[1:]:
                found = _assignment(word)
                if found:
                    self.assign(*found)
            return
        if program in MOVES:
            self.move(words[1:])
            return
        try:
            program_text = _expand(words[0], self.assigned, strict=True)[0]
        except _Unknown:
            self.found.whole = True                                # `$CMD x`, `$(...) x`: the program is not known
            return
        if not words[0].quoted and (re.search(r"[*?]|\[.+\]", program_text) or re.search(r"\{[^}]*,", program_text)):
            self.found.whole = True                                # `/bin/r? x`, `{rm,x} y`: the shell picks the program
            return
        if program_text and _basename(program_text) in self.scripts and program not in SHELLS | INTERPRETERS:
            self.shell([], [self.scripts[_basename(program_text)]], False, depth)    # `./fix.sh` written just before
        for word in words:
            if word.quoted and program_name(word.text.split(None, 1)[0] if word.text.split() else "") in RUNS:
                self.shell([word], [], False, depth)               # `env -S 'rm x'`, `flock l -c 'rm x'`: a command in quotes
        names_only = any(not w.quoted and (w.text == "-C" or w.text.startswith(FOLDER_FLAGS)) for w in words)
        names = [program_text and program_name(program_text)] + [("" if w.quoted else w.name()) for w in words[1:]]
        every = [program_name(program_text)] + [w.name() for w in words[1:]]
        runner = next((at for at, name in enumerate(every) if name in RUNNERS), None)
        if runner is not None and any(n in WRITE_VERBS | SHELLS | INTERPRETERS | {"git", "sed", "perl", "find"}
                                      for n in every[runner + 1:]):
            self.found.whole = True                                # `... | xargs rm`: the names come from its input
            return
        if program == "mkdir":
            self.make(words[1:])
        if "ln" in names or "mklink" in names:
            self.found.whole = True                                # a link made now can send a later write anywhere
            return
        interpreted = False
        for at, name in enumerate(names):
            if name in SHELLS and (at == 0 or name not in (".", "source", "eval")):
                self.shell(words[at + 1:], simple.bodies, piped and at == 0, depth)
            if name in INTERPRETERS and not interpreted:
                interpreted = True
                writing = AWK_WRITES if name in ("awk", "gawk") else CODE_WRITES
                self.code(words[at:], simple.bodies, piped and at == 0, writing, name in ("perl", "ruby", "php"))
            if name in WRITE_VERBS:
                self.verb(name, words[at + 1:], names_only, simple.bodies)
            if name == "git" and any(n in GIT_WRITES for n in names[at + 1:at + 4]):
                self.verb(name, words[at + 1:], names_only, simple.bodies)
            if name == "sed" and any(_flag(w) and (re.fullmatch(r"-\w*i\S*", w.text) or w.text.startswith("--in-place"))
                                     for w in words[at + 1:]):
                for word in words[at + 1:]:
                    self.target(word, names_only)
            if name == "perl" and any(_flag(w) and re.fullmatch(r"-\w*i\S*", w.text) for w in words[at + 1:]):
                for word in words[at + 1:]:
                    self.target(word, names_only)
            if name == "find" and any(w.text in FIND_ACTIONS for w in words[at + 1:] if not w.quoted):
                for word in words[at + 1:]:
                    self.target(word, names_only=True)

    def loop(self, words: list[Word]) -> None:
        """``for NAME in w1 w2 ...``: NAME holds each word in turn, so a place it is written into names every one of them."""
        if not words:
            return
        name = words[0].text
        if len(words) < 2 or words[1].text != "in" or name not in self.stable:
            self.assigned[name] = None
            return
        try:
            self.assigned[name] = " ".join(_expand(w, self.assigned, strict=True)[0] for w in words[2:])
        except _Unknown:
            self.assigned[name] = None

    def assign(self, name: str, value: Word) -> None:
        self.moves_codex = self.moves_codex or name.upper() == "CODEX_HOME"
        if name not in self.stable:
            self.assigned[name] = None
            return
        if value.substitutions:
            made = value.text == "$(...)" and re.match(r"\s*mktemp(?:\s|$)", value.substitutions[0])
            self.assigned[name] = (Path(tempfile.gettempdir()) / SCRATCH).as_posix() if made else None
            return
        try:
            self.assigned[name] = _expand(value, self.assigned, strict=True)[0]
        except _Unknown:
            self.assigned[name] = None

    def move(self, operands: list[Word]) -> None:
        if any(w.text == "-" for w in operands) or os.environ.get("CDPATH") or "CDPATH" in self.assigned:
            self.moved_to(None)                                    # `cd -`, or a CDPATH that may send it elsewhere
            return
        operand = next((w for w in operands if not _flag(w) and w.text.casefold() != "/d"), None)
        if operand is None:
            self.exact.add(Path.home())
            self.moved_to(Path.home())
            return
        try:
            text = _expand(operand, self.assigned, strict=True)[0]
        except _Unknown:
            self.moved_to(None)
            return
        self.found.context.append(text)
        moved = list(dict.fromkeys(_join(base, text) for base in self.dirs))
        absolute = Path(windows_path(text)).is_absolute()
        self.exact |= {_join(b, text) for b in self.dirs if _join(b, text) is not None and (absolute or b in self.exact)}
        self.union = [*self.union, *(d for d in moved if d not in self.union)]
        self.chain = moved if self.after != "||" else None        # after `||` the move may not have run

    def moved_to(self, folder: Path | None) -> None:
        self.union = self.union if folder in self.union else [*self.union, folder]
        self.chain = [folder] if self.after != "||" else None

    def make(self, operands: list[Word]) -> None:
        """``mkdir`` creates folders: a path written into one of them lands where it says."""
        for word in operands:
            if _flag(word):
                continue
            try:
                text = _expand(word, self.assigned, strict=True)[0]
            except _Unknown:
                continue
            for base in self.dirs:
                place = _join(base, text)
                while place is not None and place not in self.found.made and place != place.parent:
                    self.found.made.add(place)
                    place = place.parent

    def shell(self, args: list[Word], bodies: list[str], piped: bool, depth: int) -> None:
        try:
            texts = [_expand(w, self.assigned, strict=True)[0] for w in args]
        except _Unknown:
            self.found.whole = True                                # `eval "$X"`: the script is not known
            return
        script = next((self.scripts[_basename(t)] for t in texts if not t.startswith("-") and _basename(t) in self.scripts),
                      None)                                         # `sh fix.sh`, `. fix.sh` written just before
        inner = " ".join(texts) + "".join("\n" + b for b in [*bodies, *([script] if script else [])])
        if not inner.strip():
            if piped:
                self.found.whole = True                            # `... | sh`: the commands come from the pipe
            return
        if depth >= MAX_DEPTH:
            self.found.whole = True
            return
        try:
            commands = lex(inner, depth + 1)
        except Unreadable:
            self.found.whole = True
            return
        chain, dirs, union, after, assigned = self.chain, self.dirs, self.union, self.after, dict(self.assigned)
        stable = self.stable
        self.stable = (stable - _assigned_names(commands)) | (_stable(commands) - set(assigned))
        self.union = list(dirs)                          # the script starts where the shell is
        self.read(commands, depth + 1)
        self.union = [*union, *(d for d in self.union if d not in union)]
        self.chain, self.dirs, self.after, self.assigned, self.stable = chain, dirs, after, assigned, stable

    def code(self, words: list[Word], bodies: list[str], piped: bool, writing: re.Pattern, runs_backticks: bool) -> None:
        """An interpreter's code: its quoted and partly quoted arguments (variables put in), its here-documents, and a
        script this command wrote and runs."""
        written = [self.scripts[_basename(w.text)] for w in words[1:] if not w.quoted and _basename(w.text) in self.scripts]
        quoted = [_expand(w, self.assigned, strict=False)[0] for w in words[1:] if w.partly_quoted]
        code = "\n".join([*quoted, *bodies, *written])
        if not code and piped:
            self.found.whole = True
            return
        if not (writing.search(code) or (runs_backticks and SHELL_QUOTES.search(code))):
            return
        dirs = (None,) if re.search(r"\bchdir\b", code) else tuple(self.dirs)
        self.found.targets.append(Target(code, code.replace("\\", "/"), "", dirs, code=True, source=code))
        for word in words[1:]:
            if not word.quoted:
                self.target(word)

    def verb(self, name: str, args: list[Word], names_only: bool, bodies: list[str] = ()) -> None:
        for body in bodies:                                    # what a writing command reads can name what it writes
            self.found.targets.append(Target(body, body.replace("\\", "/"), "", tuple(self.dirs), code=True, source=body))
        if name == "cp" and self.copy(args, names_only):
            return
        for word in args:
            self.target(word, names_only)
        if name in COPY_VERBS:                                 # any argument may be the folder the others go into
            folders = [w for w in args if not _flag(w) or "=" in w.text]          # `--target-directory=DIR` included
            for folder in folders:
                for source in args:
                    if source is not folder and not _flag(source):
                        self.target(_inside(folder, source), names_only)

    def copy(self, args: list[Word], names_only: bool) -> bool:
        """``cp`` writes its destination, and the name of each source inside it when it is a folder. Only for flags
        that change nothing about where it writes; False to count every argument."""
        operands, ended = [], False
        for word in args:
            if not ended and _flag(word):
                if word.text == "--":
                    ended = True
                elif word.text.startswith("--"):
                    if not word.text.startswith(CP_SAFE_LONG):
                        return False
                elif not set(word.text[1:]) <= CP_SAFE_SHORT:
                    return False
                continue
            operands.append(word)
        if len(operands) < 2:
            return False
        *sources, destination = operands
        self.target(destination, names_only)
        if len(sources) > 1 or destination.text.endswith(("/", "\\")) or self.is_folder(destination):
            for source in sources:
                self.target(_inside(destination, source), names_only)
        return True

    def is_folder(self, word: Word) -> bool:
        """Is the word a folder, now or once the command has made it, in any folder the command may be in?"""
        try:
            text = _expand(word, self.assigned, strict=True)[0]
        except _Unknown:
            return True
        places = [_join(base, text) for base in self.dirs]
        return any(place is None or place.is_dir() or place in self.found.made for place in places)


def _inside(folder: Word, source: Word) -> Word:
    """The place ``source`` lands in when ``folder`` is a folder: the folder joined with the source's name."""
    name = source.text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    windows = source.windows.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return Word([*folder.parts, ("/" + name, "single")], [*folder.substitutions, *source.substitutions],
                folder.windows.rstrip("\\/") + "/" + windows)


def _assigned_names(commands: list[Simple]) -> set[str]:
    return {found[0] for simple in _all_simple(commands) for w in simple.words if (found := _assignment(w))}


def _basename(text: str) -> str:
    return text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].casefold()


def _join(base: Path | None, text: str) -> Path | None:
    path = Path(windows_path(text))
    if path.is_absolute():
        return path
    return None if base is None else base / path


def windows_path(text: str) -> str:
    """On Windows, Git Bash's ``/c/Users/...`` is ``C:/Users/...`` and its ``/tmp`` is the system temp folder."""
    if os.name == "nt":
        if text == "/tmp" or text.startswith("/tmp/"):
            return Path(tempfile.gettempdir()).as_posix() + text[4:]
        match = re.match(r"/([A-Za-z])(/|$)", text)
        if match:
            return f"{match.group(1).upper()}:/{text[3:]}"
    return text


def writes(command: str, cwd: Path | None) -> Writes | None:
    """Where the command writes, or None when it writes nothing. ``whole`` set: the whole command counts."""
    try:
        commands = lex(command)
    except Unreadable:
        return Writes(whole=True)
    reader = _Reader(cwd, _stable(commands))
    reader.read(commands, 0)
    found = reader.found
    if reader.moves_codex and found.targets:
        found.whole = True                                     # it writes with Codex's home moved somewhere else
    return found if found.targets or found.whole else None


def runs_code(command: str) -> bool:
    """Could the command run something the guard does not read off its words: a shell or an interpreter (of a script, a
    string or its input), a program named by a variable or a substitution, a runner such as ``xargs``? Or can it not be
    read at all?"""
    try:
        commands = lex(command)
    except Unreadable:
        return True
    stable, known = _stable(commands), {}
    for simple in _all_simple(commands):
        words = simple.words
        if words and words[0].name() == "for" and not words[0].quoted:
            continue                                           # its word list is data
        if words and all(_assignment(w) for w in words):
            for word in words:
                name, value = _assignment(word)
                known[name] = value.text if name in stable and not value.substitutions and "$" not in value.text else None
            continue
        words = words[_program_at(words):]
        if simple.expands or any(w.substitutions for w in words[:1]):
            return True
        if words and "$" in words[0].text:
            match = re.fullmatch(r"\$\{?(\w+)\}?", words[0].text)
            value = known.get(match.group(1)) if match else None
            if value is None or len(value.split()) != 1 or program_name(value) in SHELLS | INTERPRETERS | RUNNERS:
                return True                                    # `$B route` with B the bdd command line is fine
        if any(w.name() in SHELLS | INTERPRETERS | RUNNERS and (at == 0 or w.name() not in (".", "source", "eval"))
               and not (w.name() in INTERPRETERS and all(x.text in VERSION_ONLY for x in words[at + 1:]))
               for at, w in enumerate(words)):
            return True
        if any(w.quoted and program_name(w.text.split(None, 1)[0] if w.text.split() else "") in RUNS for w in words):
            return True
    return False


def program_view(command: str) -> str:
    """The command with what is data to it taken out: quoted arguments (but not a quoted program), here-documents, the
    values of assignments and the word list of a ``for`` loop. For a command that ``runs_code``, and one that cannot be
    read, the command as it is."""
    if runs_code(command):
        return command
    return "\n".join(_view(lex(command)))


def _view(commands: list[Simple]) -> list[str]:
    lines: list[str] = []
    for simple in commands:
        lines += _view(simple.nested)
        words = simple.words
        if words and words[0].name() == "for":
            continue
        program = _program_at(words)
        shown = []
        for at, word in enumerate(words):
            assignment = _assignment(word)
            if assignment:
                shown.append(assignment[0] + '=""')
            elif word.quoted and at > program:
                shown.append('""')
            else:
                shown.append(word.windows)
        shown += [f"> {word.windows}" for word in simple.redirects]
        lines.append(" ".join(shown))
    return lines


def without_data(command: str) -> str:
    """The command without the long here-document bodies a shell does not run (``cat > x <<EOF``, ``python - <<EOF``), so
    that reading every way a shell could spell it stays quick; the bodies a shell runs stay. The command as it is when it
    cannot be read."""
    try:
        commands = lex(command)
    except Unreadable:
        return command
    data = [body for simple in _all_simple(commands) if simple.bodies and not runs_code_simple(simple)
            for body in simple.bodies if len(body) > 200]
    for body in data:
        command = command.replace(body, "", 1)
    return command


def runs_code_simple(simple: Simple) -> bool:
    """Is a here-document of this command run as shell commands (a shell reads it, or it is piped on)? Interpreter code
    is not shell: its braces and quotes are not the shell's, and the raw command is still checked as it is."""
    words = simple.words[_program_at(simple.words):]
    return simple.expands or any(w.name() in SHELLS | RUNNERS for w in words) or simple.joiner in ("|", "|&")
