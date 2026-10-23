"""Directory links that need no privilege, and a removal that never touches what a link points at.

A symbolic link to a directory needs Developer Mode or administrator rights on Windows. A junction (a directory
reparse point to a folder on a local disk) needs neither, so Windows gets junctions and every other system gets
symbolic links. ``Path.is_symlink()`` is False for a junction and ``shutil.rmtree`` follows one into the real folder,
so a link is always removed with ``remove_link``, which deletes the link itself and nothing behind it.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

from .errors import UsageError

# Characters cmd.exe would read as syntax even when the command line is built without a shell string.
CMD_SYNTAX = set('&|<>^%"\r\n')
# The reparse tag of a Windows junction (a mount point). ``stat.IO_REPARSE_TAG_MOUNT_POINT`` exists on Windows only.
REPARSE_TAG_MOUNT_POINT = 0xA0000003


def is_link(path: Path) -> bool:
    """Is ``path`` itself a symbolic link or a Windows junction (whatever it points at)?"""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) == REPARSE_TAG_MOUNT_POINT


def remove_link(path: Path) -> None:
    """Remove the link ``path`` and leave the folder it points at as it is. Refuses a path that is not a link."""
    if not is_link(path):
        raise OSError(f"{path} is not a link, so it is not removed")
    if os.name == "nt" and path.is_dir():
        os.rmdir(path)  # removes a junction or a directory symlink itself, never the contents behind it
    else:
        path.unlink()


def link_directory(source: Path, target: Path) -> str:
    """Make ``target`` a link to the existing folder ``source``. Returns the kind of link made, or raises UsageError
    naming the folder and the reason."""
    for path in (source, target):
        if not path.is_absolute():
            raise UsageError(f"cannot link {source.name}: {path} is not an absolute path")
    try:
        if os.name == "nt":
            return _junction(source, target)
        os.symlink(source, target, target_is_directory=True)
        return "symlink"
    except (OSError, subprocess.SubprocessError, UsageError) as error:
        raise UsageError(f"cannot link the installed folder {source.name} ({source}) into the temporary worktree: "
                         f"{error}. Nothing was run. {platform_hint()}, then run the command again") from error


def _junction(source: Path, target: Path) -> str:
    create = getattr(_winapi_module(), "CreateJunction", None)
    if create is not None:
        create(str(source), str(target))
        return "junction"
    _mklink_junction(source, target)
    return "junction (mklink)"


def _winapi_module():
    import _winapi  # exists on Windows only; resolved when a junction is needed
    return _winapi


def _mklink_junction(source: Path, target: Path) -> None:
    """``cmd /c mklink /J``, started with an argument list and no shell string, for a Python without CreateJunction."""
    for path in (source, target):
        if CMD_SYNTAX & set(str(path)):
            raise UsageError(f"{path} holds a character cmd.exe would read as syntax, so mklink is not used for it")
    cmd = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
    done = subprocess.run([str(cmd), "/c", "mklink", "/J", str(target), str(source)],
                          capture_output=True, text=True, check=False, timeout=30)
    if done.returncode != 0:
        raise OSError((done.stderr or done.stdout).strip() or f"mklink exited with status {done.returncode}")


def platform_hint() -> str:
    """What to do when a folder cannot be linked."""
    if sys.platform == "win32":
        return ("To fix it, keep the project and the temporary folder (TEMP) on local NTFS drives, which a junction "
                "needs, or turn on Developer Mode so symbolic links work")
    return "To fix it, make the temporary folder (TMPDIR) writable and the project's folder readable"
