"""Where a shell command writes, for the commands whose writes can be read off their words.

The guard used to count a command as a write when a write word appeared anywhere in it (``Move`` in a quoted argument, a
``>`` inside a regular expression), and as a write to a protected file when that file's name appeared anywhere in it.
For a command built only from plain constructs and known programs (``plain``), this reads it into words, quotes,
here-documents, separators, redirections and changes of folder, and returns what it writes to: the targets of its
output redirections, the arguments of the commands that change files, and the code of an interpreter whose code writes,
with the folders a relative path in each may land in. The guard then checks its protections against those alone.

Everything else is judged by the old rule: a shell or a runner of other programs (``sh``, ``eval``, ``make``,
``xargs``, ``sudo``), a program the reader does not know, a command or process substitution, an alias or a function, a
program word that is not a known value, a moved home or ``CDPATH``, ``pushd`` and ``popd``, links, input fed to an
interpreter, and anything that does not read cleanly. Reading those exactly would mean modelling a shell, and every
model missed something; the list of what is read is short so that it can be checked.
"""
from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

WRITE_VERBS = {"tee", "cp", "mv", "rm", "truncate", "dd", "install", "chmod", "touch"}
COPY_VERBS = {"cp", "mv", "install"}                    # they write into a folder too
INTERPRETERS = {"python", "py", "node", "tsx"}
PACKAGE_TOOLS = {"npm", "pnpm", "yarn", "npx", "bun", "pip", "uv", "poetry", "pipx", "pipenv", "conda"}
# Programs no option or argument of which writes a file, runs a command or loads code. Any other program (sed, awk,
# git, find, sort, ...) makes the command one that is judged whole.
READERS = {"cat", "grep", "egrep", "fgrep", "ls", "head", "tail", "wc", "cut", "tr", "diff", "cmp", "jq", "echo", "printf",
           "stat", "du", "df", "which", "realpath", "readlink", "basename", "dirname", "date", "uname", "pwd", "true", "false",
           "test", "[", "[[", "]", "]]", "sleep", "nl", "comm", "paste", "fold", "md5sum", "sha1sum", "sha256sum", "seq",
           "mkdir", "bdd"}
KEYWORDS = {"for", "do", "done", "if", "then", "else", "elif", "fi", "while", "until", "{", "}", "!", "time"}
PREFIXES = {"env", "time", "nice", "timeout", "do", "then", "else", "elif", "if", "while", "until", "{", "}", "!"}
PROGRAMS = READERS | WRITE_VERBS | INTERPRETERS | PACKAGE_TOOLS | KEYWORDS | {"cd", "export"}
RUN_BY_TOOLS = INTERPRETERS | WRITE_VERBS | {"sh", "bash", "zsh", "dash", "cmd", "powershell", "pwsh", "eval", "make", "awk",
                                             "gawk"}
MOVES = {"cd"}
PURE_READERS = {"pwd", "mktemp", "date", "basename", "dirname", "realpath", "cat", "ls", "echo", "printf", "head", "tail", "wc"}
MKTEMP_FLAGS = {"-d", "-q", "-u", "--directory", "--quiet", "--dry-run"}   # `mktemp -p dir`, `mktemp x.XXX` make a file elsewhere
PREFIX_FLAGS = {("env", "-i"), ("time", "-p"), ("nice", "-n")}       # the only prefix options a plain command may use
MAX_FOLDERS = 32
MAX_JOINED = 40                                         # words of an unknown program joined each to each
# A command may set no variable that moves the folders or steers what a program runs or loads (``PATH``,
# ``NODE_OPTIONS``, ``GIT_*``, ``LD_PRELOAD`` ...), nor one that is in its environment already.
STEERS = re.compile(r"HOME|CDPATH|PWD|OLDPWD|USERPROFILE|CODEX_HOME|IFS|ENV|BASH_ENV|SHELLOPTS|BASHOPTS|GLOBIGNORE|PS4|"
                    r"PROMPT_COMMAND|TMPDIR|TEMP|TMP|PAGER|EDITOR|VISUAL|SHELL|(?:PATH|GIT|NODE|NPM|PYTHON|LD|DYLD|BUN|DENO|"
                    r"PNPM|YARN|UV|PIP|CONDA|POETRY|PERL|RUBY|JQ|LESS|GREP|GREENLIGHT|CLAUDE)\w*|npm_config_\w*|\w*PATH",
                    re.IGNORECASE)
FOLDER_FLAGS = ("--directory", "--chdir", "--git-dir", "--work-tree", "--prefix", "--cwd", "--dir")
# The flags with which `cp` writes only its destination (a folder target, a link or a hard link writes elsewhere too).
CP_SAFE_SHORT = set("aRrfpvniuPLdHx")
CP_SAFE_LONG = ("--recursive", "--force", "--preserve", "--no-preserve", "--verbose", "--no-clobber", "--interactive",
                "--update", "--archive", "--dereference", "--no-dereference", "--parents")
HARMLESS_TARGETS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty", "nul", "con"}
GROUPING = {"{", "}", "!", "(", ")"}
# What makes interpreter code a write: Python and Node spellings, code that runs a shell, and code that calls by a
# computed name.
CODE_WRITES = re.compile(
    r"write_text|write_bytes|(?<!stdout)(?<!stderr)(?<!buffer)\.write\(|\.writelines\(|:write\("
    r"|open\((?:[^()]|\([^()]*\))*?[\"'][rwabxt+]*[wax+][rwabxt+]*[\"']"
    r"|\bos\.(?:remove|rename|replace|unlink|rmdir|removedirs|truncate|symlink|link|chmod|makedirs|mkdir)\b|\bshutil\."
    r"|\.(?:unlink|rename|rmdir|touch|symlink_to|hardlink_to|chmod|mkdir)\("
    r"|\bfs(?:\.promises|p)?\.(?!(?:read|exists|stat|lstat|access|realpath|opendir|watch|constants)\w*)\w+"
    r"|\b(?:writeFile|appendFile|createWriteStream|copyFile|renameSync|unlinkSync|rmSync|rmdirSync|truncateSync|"
    r"symlinkSync|chmodSync|mkdirSync)\w*\s*\("
    r"|\bunlink\b|subprocess|\bos\.(?:system|popen|exec\w*|spawn\w*)|\bPopen\b|child_process|\bexec\w*\b|\bspawn\w*\b"
    r"|\bsystem\b|\bgetattr\b|__import__|\bimportlib\b|\beval\b|\bcompile\s*\(")
# Other interpreters' writes, for a command read whole: it is checked if it looks like a write in any of these spellings.
OTHER_CODE = re.compile(r"(?:^|[\s;&|(`])(?:ruby|php|perl|lua|luajit|pypy\w*|ipython|jython|groovy|julia|rscript|osascript|"
                        r"wscript|cscript)(?:\.exe)?\s|\bFile\.(?:write|open|delete|binwrite|rename|unlink)|file_put_contents|"
                        r"\bfopen\b|FileUtils|\bqx\b|\bmklink\b|Deno\.\w*[Ww]rite|Bun\.write|"
                        r"\bopen\s*\(?\s*\w+\s*,\s*[\"']?\s*[>+]", re.IGNORECASE)
_VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+)|(\{[^}]*\}|[@*#?$!\-]))")
_ASSIGNMENT = re.compile(r"([A-Za-z_]\w*)(\+?)=")
_SUFFIX = re.compile(r"\.(?:exe|cmd|bat|ps1)$")
_VERSION = re.compile(r"(?<=[a-z])[\d.]+$")
MAX_DEPTH = 4
MAX_LENGTH = 400_000                                    # longer than this is not read: the old rule applies


class Unreadable(Exception):
    """The command cannot be read reliably enough to say where it writes."""


@dataclass
class Word:
    """A shell word: its parts with how each was quoted (``plain``, ``double``, ``single`` or ``ansi``)."""
    parts: list[tuple[str, str]] = field(default_factory=list)
    substitutions: list[str] = field(default_factory=list)    # the commands of its command substitutions
    pieces: list[str] = field(default_factory=list)           # the word read with each backslash as a folder separator

    def add(self, text: str, how: str, windows: str | None = None) -> None:
        if self.parts and self.parts[-1][1] == how:
            self.parts[-1] = (self.parts[-1][0] + text, how)
        else:
            self.parts.append((text, how))
        self.pieces.append(text if windows is None else windows)

    @property
    def windows(self) -> str:
        return "".join(self.pieces)

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
    segment = text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1].casefold()
    return _VERSION.sub("", _SUFFIX.sub("", segment))


@dataclass
class Simple:
    words: list[Word] = field(default_factory=list)
    redirects: list[Word] = field(default_factory=list)    # where its output goes
    inputs: list[Word] = field(default_factory=list)       # what its input is read from (`< file`)
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
    opaque: bool = False                                   # a program word is a variable or a pattern with no known value
    made: set[Path] = field(default_factory=set)           # the folders a `mkdir` in the command creates
    every: bool = False                                    # every word of a program not known counts as written


# Write forms of programs that are not read exactly, matched in the command's text whatever its quoting: sed's `w`, `W`
# and `e` commands, `-i` and `-f`; git's `-c` and `--config-env`; awk's in-place, include and load; sort's output and
# compress program; uniq's output operand; `xxd -r`; tree's and gh's output and download; any output option. They only
# decide that the words such a program is given are checked; a false match refuses only a command that is also given a
# protected path.
WRITE_HINTS = re.compile(
    r"\bsed\b[^|;&\n]*?(?:[\s\"'/;:{}!$,\d](?:[wWe])(?=[\s\"';}]|$)|[\s\"'](?:-\w*[if]|--in\S*|--f\S*))"
    r"|\bgit\b[^|;&\n]*?[\s\"'](?:-c|-C|--config-env\S*|--output\S*|-o|--work-tree\S*|--git-dir\S*|checkout\S*|restore|reset"
    r"|stash|apply|rm|mv|clean|merge|pull|switch|rebase|cherry-pick|am|read-tree|worktree|update-index|archive)(?=[\s\"'=]|$)"
    r"|\b[gnm]?awk\b[^|;&\n]*?(?:[\s\"']-\w*i|--in\S*|inplace|@include|@load)"
    r"|\bsort\b[^|;&\n]*?[\s\"'](?:-\w*o|--o\S*|--co\S*)|\buniq\b|\bxxd\b[^|;&\n]*?-\w*r|\btree\b[^|;&\n]*?-\w*o"
    r"|\bgh\b[^|;&\n]*?(?:download|checkout|clone|[\s\"']-O)"
    r"|\b(?:xargs|shred|unlink|patch|rsync|tar|unzip|curl|wget|rename|mklink|robocopy|xcopy)\b"
    r"|(?:^|[\s\"'])(?:-o|-O|--out\S*|--write\S*|--save\S*|--dest\S*|--target\S*)(?=[\s\"'=]|$)")


# -- reading the command ------------------------------------------------------------------------------------------
class _Lexer:
    def __init__(self, text: str, depth: int):
        self.text, self.at, self.depth = text, 0, depth
        self.commands: list[Simple] = []
        self.current = Simple()
        self.word: Word | None = None
        self.heredocs: list[tuple[str, bool, Simple, bool]] = []
        self.next_is: str | None = None                   # "target", "delimiter", "string", "input"
        self._strip_tabs = False

    def run(self) -> list[Simple]:
        while self.at < len(self.text):
            self.step()
        self.end_word()
        if self.heredocs or self.next_is is not None:
            raise Unreadable("a here-document or a redirection is not finished")
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
        elif role == "input":
            self.current.inputs.append(word)
        elif role == "delimiter":
            self.heredocs.append((word.text, self._strip_tabs, self.current, not word.partly_quoted))
        elif role == "string":
            self.current.bodies.append(word.text)
        else:
            self.current.words.append(word)

    def end_command(self, joiner: str) -> None:
        self.end_word()
        if self.next_is is not None:
            raise Unreadable("a redirection has no target")
        if self.current.words or self.current.redirects or self.current.bodies or self.current.nested or self.current.inputs:
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
        elif char == "\x00":
            raise Unreadable("a NUL character")
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
        self.next_is = {"<<": "delimiter", "<<-": "delimiter", "<<<": "string", "<": "input", "<&": "input"}.get(op, "target")

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
    if len(command) > MAX_LENGTH:
        raise Unreadable("the command is too long to read")
    return _Lexer(command, depth).run()


def _all_simple(commands: list[Simple]):
    for simple in commands:
        yield from _all_simple(simple.nested)
        yield simple


# -- variables -----------------------------------------------------------------------------------------------------
class _Unknown(Exception):
    """A word holds a value that cannot be known here."""


SCRATCH_FOLDER = "greenlight-scratch"                    # where `$(mktemp -d)` is taken to point


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
                 [word.windows[match.end():]])
    return match.group(1), value


def _flag(word: Word) -> bool:
    return word.text.startswith("-")                        # `"-t" dir` is the option it spells, quoted or not


def _program_at(words: list[Word]) -> int:
    """Where the program word is: after the prefixes (``timeout 20``, ``do``, ``{``) and the assignments and flags that
    belong to them."""
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
    ``do``, or in a declaration may hold another value, so it is not known."""
    counts: dict[str, int] = {}
    unknown: set[str] = set()
    for simple in _all_simple(commands):
        words = simple.words
        plain = bool(words) and all(_assignment(w) for w in words)
        for word in words:
            found = _assignment(word) if not word.quoted else None
            if found:
                counts[found[0]] = counts.get(found[0], 0) + 1
                if not plain or re.match(r"[A-Za-z_]\w*\+=", word.parts[0][0]):
                    unknown.add(found[0])
        if words and words[0].name() == "for" and len(words) > 1:
            counts[words[1].text] = counts.get(words[1].text, 0) + 1
    return {name for name, count in counts.items() if count == 1 and name not in unknown}


def _known_values(commands: list[Simple]) -> dict[str, str | None]:
    """The values plain assignments give stable variables (None: not a known literal)."""
    stable, known = _stable(commands), {}
    for simple in _all_simple(commands):
        words = simple.words
        if words and all(_assignment(w) for w in words):
            for word in words:
                name, value = _assignment(word)
                text = value.text
                known[name] = text if name in stable and not value.substitutions and "$" not in text else None
    return known


def _program_value(word: Word, known: dict[str, str | None]) -> str | None:
    """The value of a program word that is one variable (``$P``, ``"${P}"``), if the command gave it one."""
    if word.substitutions:
        return None
    match = re.fullmatch(r"\$\{?(\w+)\}?", word.text)
    return known.get(match.group(1)) if match else None


def _program(words: list[Word], known: dict[str, str | None]) -> str | None:
    """The name of the program a simple command runs, the bdd command line run by ``sh`` included; None when it is not
    a literal or a known single word."""
    if not words:
        return ""
    first = words[0]
    if "$" in first.text or first.substitutions:
        value = _program_value(first, known)
        if value is not None and _bdd_by_sh(value):
            return "bdd"
        if value is None or len(value.split()) != 1:
            return None
        text = value
    else:
        text = first.text
    if re.search(r"[*?]|\[.+\]|\{[^}]*,", text) and not first.quoted:
        return None                                            # the shell picks the program by a pattern
    name = program_name(text)
    if name in ("sh", "bash") and len(words) > 1 and program_name(_program_value(words[1], known) or words[1].text) == "bdd":
        return "bdd"                                           # `sh "$CLAUDE_PLUGIN_ROOT/tools/bdd/bdd" route`
    return name


def _bdd_by_sh(value: str) -> bool:
    """``B="sh <plugin>/tools/bdd/bdd"; $B route``: the bdd command line, run by sh."""
    words = value.split()
    return len(words) == 2 and program_name(words[0]) in ("sh", "bash") and program_name(words[1]) == "bdd"


def _installed_runner(text: str) -> bool:
    """A program the project installed, run from its folder (``node_modules/.bin/tsc``, ``.venv/bin/pytest``)."""
    path = text.replace("\\", "/").casefold()
    return bool(re.search(r"(?:^|/)node_modules/\.bin/[^/]+$|(?:^|/)\.?venv/(?:bin|scripts)/[^/]+$", path))


def judge(commands: list[Simple]) -> str:
    """How exactly the command can be read.

    ``PLAIN`` (an empty text): it is built only from known programs (``PROGRAMS``, or one the project installed, given
    only paths and flags) named by a literal or a known variable, with no prefix option, no variable that steers a
    program or the folders, no here-document that runs a substitution, no input fed to an interpreter or a package tool,
    and substitutions that only read (``$(pwd)``, ``$(mktemp -d)``). Its writes are read off its words exactly.

    ``OTHER``: the same, except that some programs are not known (``sed``, ``git``, ``awk`` ...). Their options are not
    modelled: every word they are given counts as written (``every``).

    ``UNREAD``: something this reading does not follow (a prefix option, a substituting here-document); ``WRITES``:
    something that may write or run code that no word shows (an installed shell, a program word with no known value, a
    variable that steers what runs, a substitution that runs more than a reader, input fed to an interpreter). Both are
    judged whole by the old rule; ``WRITES`` even when no write word shows."""
    known = _known_values(commands)
    verdicts = {PLAIN}
    for simple in commands:
        if not _reads_only(simple.nested):
            return WRITES                                      # `echo $(git checkout x)`: what runs inside is not read here
        if simple.expands:
            verdicts.add(UNREAD)
        words = simple.words
        for word in words:
            found = _assignment(word)
            if (found and found[0] not in HARMLESS_VARIABLES and (STEERS.fullmatch(found[0]) or found[0] in os.environ)
                    and not re.fullmatch(r"\$\{?" + found[0] + r"\}?", found[1].text)):
                return WRITES                                  # `PATH=x:$PATH cat`, `NODE_OPTIONS=--require x node`
        if words and all(_assignment(w) for w in words):
            continue
        start = _program_at(words)
        while start < len(words) and _assignment(words[start]):
            start += 1
        rest = words[start:]
        prefix = ""
        for word in words[:start]:
            if not word.quoted and word.name() in PREFIXES:
                prefix = word.name()
            elif not (_assignment(word) or word.text.isdigit() or (prefix, word.text) in PREFIX_FLAGS):
                verdicts.add(UNREAD)                           # `env -S 'rm x'`, `env --chdir=x`, `timeout -s KILL 5`
        if not rest:
            continue
        name = _program(rest, known)
        if name is None:
            return WRITES                                      # `$X args`, `$(echo rm) x`: the program is not known
        installed = _installed_runner(rest[0].text) and name not in PROGRAMS
        if installed and (name in INSTALLED_SHELLS or any(w.partly_quoted for w in rest)):
            return WRITES                                      # `.venv/bin/bash -c ...`, an installed tool given code
        if name in INTERPRETERS | PACKAGE_TOOLS and simple.inputs:
            return WRITES                                      # `python < script.py`
        if name in PACKAGE_TOOLS and any(w.name() in RUN_BY_TOOLS for w in rest[1:]):
            return WRITES                                      # `uv run python -c ...`, `npx --no-install tsx -e ...`
        if name not in PROGRAMS and not installed:
            verdicts.add(OTHER)
    return next(v for v in (UNREAD, OTHER, PLAIN) if v in verdicts)


PLAIN, WRITES, OTHER, UNREAD = "", "writes", "other", "unread"
INSTALLED_SHELLS = {"sh", "bash", "zsh", "dash", "pwsh", "powershell", "cmd"}
HARMLESS_VARIABLES = {"PYTHONIOENCODING", "PYTHONUTF8", "PYTHONUNBUFFERED", "PYTHONDONTWRITEBYTECODE", "NO_COLOR",
                      "FORCE_COLOR", "CI", "TZ", "LANG", "LC_ALL", "NODE_ENV"}


def plain(commands: list[Simple]) -> bool:
    return judge(commands) == PLAIN


def _reads_only(commands: list[Simple]) -> bool:
    """Do these commands (a substitution's) only read: known readers, with no output redirection and nothing nested?"""
    for simple in commands:
        words = simple.words[_program_at(simple.words):]
        if simple.nested or simple.redirects or simple.bodies or (words and _program(words, {}) not in PURE_READERS):
            return False
        if words and _program(words, {}) == "mktemp" and any(w.text not in MKTEMP_FLAGS for w in words[1:]):
            return False
    return True


def _unknown_program(simple: Simple, known: dict[str, str | None]) -> bool:
    """Does this simple command run a program that is not read exactly?"""
    words = simple.words
    start = _program_at(words)
    while start < len(words) and _assignment(words[start]):
        start += 1
    if start >= len(words) or all(_assignment(w) for w in words):
        return False
    return _program(words[start:], known) not in PROGRAMS and not _installed_runner(words[start].text)


# -- what the commands write ---------------------------------------------------------------------------------------
class _Reader:
    def __init__(self, cwd: Path | None, stable: set[str]):
        self.assigned: dict[str, str | None] = {}
        self.stable = stable
        self.union: list[Path | None] = [cwd]           # every folder the command may be in by now
        self.chain: list[Path | None] | None = None      # the folders after a `cd ... &&`, for the rest of that chain
        self.dirs = self.union
        self.found = Writes()
        self.scripts: dict[str, str] = {}                # the scripts the command writes, by file name
        self.exact: set[Path] = set()                    # folders a `cd` reached for sure (from an absolute path)
        self.after = ""                                  # the operator before the command being read

    def read(self, commands: list[Simple]) -> None:
        chained = False
        for simple in commands:
            if not chained:
                self.chain = None
            self.dirs = self.chain if self.chain is not None else self.union
            self.read_simple(simple)
            chained = simple.joiner == "&&"
            self.after = simple.joiner

    def every(self, commands: list[Simple]) -> None:
        """``read`` for a command some programs of which are not known. A known one is read as in ``read``, unless it
        feeds an unknown one through a pipe (``echo x | xargs rm``: its words may become that one's). For an unknown one
        every word counts as written, and so does each word inside each other word (``ln -t folder file``), each
        here-document and each script the command wrote; after it the folder is not known (``pushd``, a function,
        ``source`` may move it)."""
        self.found.every = True
        known = _known_values(commands)
        unknown = [_unknown_program(simple, known) for simple in commands]
        piped, group = [False] * len(commands), []
        for at, simple in enumerate(commands):
            group.append(at)
            if simple.joiner not in ("|", "|&"):
                for member in group:
                    piped[member] = any(unknown[m] for m in group if m > member)   # what it prints, the other reads
                group = []
        chained = False
        for at, simple in enumerate(commands):
            if not chained:
                self.chain = None
            self.dirs = self.chain if self.chain is not None else self.union
            if unknown[at] or piped[at]:
                self.every_word(simple)
            else:
                self.read_simple(simple)
            chained = simple.joiner == "&&"
            self.after = simple.joiner

    def every_word(self, simple: Simple) -> None:
        self.remember_script(simple, simple.words)
        for word in simple.redirects:
            self.target(word)
        for data in [*simple.bodies, *self.scripts.values()]:
            self.found.targets.append(Target(data, data.replace("\\", "/"), "", tuple(self.dirs), code=True, source=data))
        words = [w for w in simple.words if w.quoted or not (w.text in GROUPING or w.name() in PREFIXES)]
        names_only = any(w.text.startswith(("-C", *FOLDER_FLAGS)) for w in words)
        for word in words[1:]:
            self.target(word, names_only)
        operands = [w for w in words[1:] if not _flag(w) or "=" in w.text]
        if len(operands) > MAX_JOINED:
            self.found.whole = True                            # too many words to join each to each: the old rule
        else:
            for folder in operands:
                for source in operands:
                    if source is not folder:
                        self.target(_inside(folder, source), names_only)
        self.moved_to(None)

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
        """A file the command writes may be run by it next: its here-document, or what ``echo`` or ``printf`` print
        (their escapes decoded, as ``printf`` and ``echo -e`` do)."""
        data = "\n".join(simple.bodies)
        if not data and words and words[0].name() in ("echo", "printf"):
            data = " ".join(_expand(w, self.assigned, strict=False)[0] for w in words[1:])
            try:
                data = data.encode("utf-8").decode("unicode_escape")
            except UnicodeDecodeError:
                pass
        written = [*simple.redirects, *(words[1:] if words and words[0].name() == "tee" else [])]   # `tee x.py <<EOF`
        for word in written:
            if data and not _flag(word):
                self.scripts[_basename(word.text)] = data

    def read_simple(self, simple: Simple) -> None:
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
            start += 1                                         # `FOO=1 cmd`: for that command only
        words = words[start:]
        self.remember_script(simple, words)
        if not words:
            return
        program = _program(words, self.assigned)
        if program == "export":
            for word in words[1:]:
                found = _assignment(word)
                if found:
                    self.assign(*found)
            return
        if program in MOVES:
            self.move(words[1:])
            return
        names_only = any(w.text == "-C" or w.text.startswith(FOLDER_FLAGS) for w in words)
        if program == "mkdir":
            self.make(words[1:])
        if program in INTERPRETERS:
            self.code(words, simple.bodies)
        if program in WRITE_VERBS:
            self.verb(program, words[1:], names_only)

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
        if name not in self.stable:
            self.assigned[name] = None
            return
        if value.substitutions:
            made = value.text == "$(...)" and re.match(r"\s*mktemp(?:\s|$)", value.substitutions[0])
            self.assigned[name] = (Path(tempfile.gettempdir()) / SCRATCH_FOLDER).as_posix() if made else None
            return
        try:
            self.assigned[name] = _expand(value, self.assigned, strict=True)[0]
        except _Unknown:
            self.assigned[name] = None

    def move(self, operands: list[Word]) -> None:
        if any(w.text == "-" for w in operands) or os.environ.get("CDPATH"):
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
        if len(self.union) > MAX_FOLDERS:
            self.union = [None]                                    # too many places to follow: a written name counts by name
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

    def code(self, words: list[Word], bodies: list[str]) -> None:
        """An interpreter's code: its quoted and partly quoted arguments (variables put in), its here-documents, and a
        script this command wrote and runs."""
        try:
            [_expand(w, self.assigned, strict=True) for w in _code_words(words) if "$" in w.text]
        except _Unknown:
            self.found.whole = self.found.opaque = True             # `python -c "$C"`: the code is not known
            return
        written = [self.scripts[_basename(w.text)] for w in words[1:] if not w.quoted and _basename(w.text) in self.scripts]
        quoted = [_expand(w, self.assigned, strict=False)[0] for w in words[1:] if w.partly_quoted or "$" in w.text]
        code = "\n".join([*quoted, *bodies, *written])
        if not CODE_WRITES.search(code):
            return
        dirs = (None,) if re.search(r"\bchdir\b", code) else tuple(self.dirs)
        self.found.targets.append(Target(code, code.replace("\\", "/"), "", dirs, code=True, source=code))
        for word in words[1:]:
            if not word.quoted:
                self.target(word)

    def verb(self, name: str, args: list[Word], names_only: bool) -> None:
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


def _code_words(words: list[Word]) -> list[Word]:
    """The words an interpreter runs as code: the one after ``-c``, ``-e``, ``-p``, ``--eval`` or ``--print`` (on its own
    or ending a cluster such as ``-Ic``), and such an option with its code attached (``-c'...'``, ``--eval=...``), quoted
    or not. A script's path and its arguments are not code."""
    found = []
    for at, word in enumerate(words[1:], 1):
        text = word.text
        if re.fullmatch(r"-[A-Za-z]*[cep]|--(?:eval|print)", text) and at + 1 < len(words):
            found.append(words[at + 1])
        elif re.match(r"-[A-Za-z]*[cep].|--(?:eval|print)=", text):
            found.append(word)
    return found


def _inside(folder: Word, source: Word) -> Word:
    """The place ``source`` lands in when ``folder`` is a folder: the folder joined with the source's name."""
    name = source.text.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    windows = source.windows.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return Word([*folder.parts, ("/" + name, "single")], [*folder.substitutions, *source.substitutions],
                [folder.windows.rstrip("\\/") + "/" + windows])


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
    """Where a ``plain`` command writes, or None when it writes nothing. For any other command (and one that cannot be
    read) a ``whole`` result: the caller judges the command by the old rule."""
    try:
        commands = lex(command)
    except Unreadable:
        return Writes(whole=True)
    verdict = judge(commands)
    if verdict in (WRITES, UNREAD):
        return Writes(whole=True, opaque=verdict == WRITES)
    reader = _Reader(cwd, _stable(commands))
    if verdict == OTHER:
        reader.every(commands)
    else:
        reader.read(commands)
    found = reader.found
    return found if found.targets or found.whole else None


# -- the programs a command runs, for the install checks --------------------------------------------------------------
PACKAGE_WORDS = {"install", "i", "add", "ci", "sync", "update", "up", "upgrade", "remove", "rm", "uninstall", "un", "exec",
                 "dlx", "x", "link", "global", "get"}


@dataclass(frozen=True)
class Programs:
    view: str                      # the command with its data taken out, or the command itself (see ``programs``)
    unknown: bool                  # a program word that cannot be known is given a package-tool subcommand


def programs(command: str) -> Programs:
    """The programs a command runs. For a ``plain`` command the view is the command with what is data to it taken out:
    quoted arguments of programs other than package tools, here-documents, and the word list of a ``for`` loop, with every
    variable the command gave a known value put in (``P=pnpm; $P add x`` runs ``pnpm add x``). For any other command, and
    one that cannot be read, the view is the command as it is. ``unknown``: a program word that holds a variable or a
    substitution with no known value (``$PM install``) is given a package-tool subcommand."""
    try:
        commands = lex(command)
    except Unreadable:
        return Programs(command, False)
    known = _known_values(commands)
    unknown = False
    for simple in _all_simple(commands):
        words = simple.words[_program_at(simple.words):]
        if words and (words[0].substitutions or "$" in words[0].text) and _program_value(words[0], known) is None:
            unknown = unknown or any(w.text.casefold() in PACKAGE_WORDS for w in words[1:] if not _flag(w))
    view = "\n".join(_view(commands, known)) if plain(commands) else command
    return Programs(view, unknown)


def _view(commands: list[Simple], known: dict[str, str | None]) -> list[str]:
    lines: list[str] = []
    for simple in commands:
        words = simple.words
        if words and words[0].name() == "for":
            continue
        program = _program_at(words)
        runs = _program(words[program:], known) in PACKAGE_TOOLS | INTERPRETERS | {"bdd"}   # their quoted words are not data
        shown = []
        for at, word in enumerate(words):
            assignment = _assignment(word)
            if assignment:
                shown.append(assignment[0] + '=""')
            elif word.quoted and at > program and not runs:
                shown.append('""')
            else:
                shown.append(_known_text(word.text, known))
        shown += [f"> {word.windows}" for word in simple.redirects]
        lines.append(" ".join(shown))
        if any(w.windows != w.text for w in words):
            lines.append(" ".join(_known_text(w.windows, known) for w in words))   # `C:\Tools\npm.cmd`
        if runs:
            lines += simple.bodies                             # an interpreter's here-document is its code
    return lines


def _known_text(text: str, known: dict[str, str | None]) -> str:
    """The text with the variables the command gave a known value put in, and no other."""
    return _VARIABLE.sub(lambda m: known.get(m.group(1) or m.group(2) or "") or m.group(0), text)


def without_data(command: str) -> str:
    """The command without the long here-document bodies a shell does not run (``cat > x <<EOF``, ``python - <<EOF``), so
    that reading every way a shell could spell it stays quick; the bodies a shell runs stay. The command as it is when it
    cannot be read."""
    try:
        commands = lex(command)
    except Unreadable:
        return command
    data = [body for simple in _all_simple(commands) if simple.bodies and not _runs_shell(simple)
            for body in simple.bodies if len(body) > 200]
    for body in data:
        command = command.replace(body, "", 1)
    return command


def _runs_shell(simple: Simple) -> bool:
    """Is a here-document of this command run as shell commands: anything but a known program reads it, or it is piped
    on? Interpreter code is not shell: its braces and quotes are not the shell's, and the raw command is still checked."""
    words = simple.words[_program_at(simple.words):]
    name = _program(words, {})
    return simple.expands or name not in PROGRAMS or simple.joiner in ("|", "|&")
