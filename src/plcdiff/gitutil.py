"""Git integration: textconv driver setup and diffing a revision range."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from plcdiff.loader import looks_supported

DRIVER = "plcdiff"
DEFAULT_PATTERNS = ("*.L5X", "*.l5x")


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: str | Path | None = None, check: bool = True) -> bytes:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise GitError(proc.stderr.decode(errors="replace").strip() or f"git {args[0]} failed")
    return proc.stdout


def repo_root(cwd: str | Path | None = None) -> Path:
    return Path(git("rev-parse", "--show-toplevel", cwd=cwd).decode().strip())


def install(
    global_: bool = False,
    patterns: tuple[str, ...] = DEFAULT_PATTERNS,
    cwd: str | Path | None = None,
    command: str = "plcdiff textconv",
) -> list[str]:
    """Register the textconv driver and map file patterns to it.

    Returns human-readable lines describing what was changed.
    """
    scope = ["--global"] if global_ else []
    git("config", *scope, f"diff.{DRIVER}.textconv", command, cwd=cwd)
    git("config", *scope, f"diff.{DRIVER}.cachetextconv", "true", cwd=cwd)
    flag = " --global" if global_ else ""
    done = [f'git config{flag} diff.{DRIVER}.textconv "{command}"']
    if global_:
        attr_path = git("config", "--global", "core.attributesFile", cwd=cwd, check=False)
        target = (
            Path(attr_path.decode().strip()).expanduser()
            if attr_path.strip()
            else Path.home() / ".config" / "git" / "attributes"
        )
    else:
        target = repo_root(cwd) / ".gitattributes"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    lines = existing.splitlines()
    added = []
    for pattern in patterns:
        line = f"{pattern} diff={DRIVER}"
        if line not in lines:
            lines.append(line)
            added.append(line)
    if added:
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        done.append(f"added to {target}: " + "; ".join(added))
    else:
        done.append(f"{target} already maps {', '.join(patterns)}")
    return done


@dataclass
class FileChange:
    path: str
    old_path: str
    old: bytes
    new: bytes


def _show(rev: str, path: str, cwd: str | Path | None) -> bytes:
    return git("show", f"{rev}:{path}", cwd=cwd, check=False)


def changed_files(
    rev_range: str | None, paths: list[str] | None = None, cwd: str | Path | None = None
) -> list[FileChange]:
    """Supported files changed in ``A..B``, ``A`` (vs. working tree) or HEAD vs. tree."""
    if rev_range and ".." in rev_range:
        base, _, head = rev_range.partition("..")
        base = base.lstrip(".") or "HEAD"
        head = head.lstrip(".") or "HEAD"
    else:
        base, head = rev_range or "HEAD", ""
    args = ["diff", "--name-status", "-M", "-z", base]
    if head:
        args.append(head)
    if paths:
        args += ["--", *paths]
    raw = git(*args, cwd=cwd).decode("utf-8", errors="replace").split("\0")
    root = repo_root(cwd)
    out: list[FileChange] = []
    i = 0
    while i < len(raw) and raw[i]:
        status = raw[i]
        if status.startswith(("R", "C")):
            old_path, new_path = raw[i + 1], raw[i + 2]
            i += 3
        else:
            old_path = new_path = raw[i + 1]
            i += 2
        if not looks_supported(new_path):
            continue
        old = b"" if status.startswith("A") else _show(base, old_path, root)
        if status.startswith("D"):
            new = b""
        elif head:
            new = _show(head, new_path, root)
        else:
            new = (root / new_path).read_bytes()
        out.append(FileChange(new_path, old_path, old, new))
    return out
