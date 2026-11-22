"""Command line interface: ``plcdiff textconv|diff|git|install``."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from plcdiff import __version__
from plcdiff.diff import BlockDiff, diff_documents
from plcdiff.gitutil import DEFAULT_PATTERNS, GitError, changed_files, install
from plcdiff.loader import UnsupportedFormat, load, loads
from plcdiff.render import render
from plcdiff.report import json_report, markdown_report, text_report


def _use_color(choice: str) -> bool:
    if choice == "always":
        return True
    if choice == "never" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _report(fmt: str, diffs: list[BlockDiff], old: str, new: str, color: bool) -> str:
    if fmt == "markdown":
        return markdown_report(diffs, old, new)
    if fmt == "json":
        return json_report(diffs, old, new)
    return text_report(diffs, old, new, color=color)


def cmd_textconv(args: argparse.Namespace) -> int:
    data = open(args.file, "rb").read()  # noqa: SIM115
    try:
        doc = loads(data, name=args.file, include_values=not args.no_values)
    except UnsupportedFormat:
        # Never break `git diff`: hand unknown files through untouched.
        sys.stdout.buffer.write(data)
        return 0
    sys.stdout.write(render(doc))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    try:
        old = load(args.old, include_values=not args.no_values)
        new = load(args.new, include_values=not args.no_values)
    except (UnsupportedFormat, OSError) as exc:
        print(f"plcdiff: {exc}", file=sys.stderr)
        return 2
    diffs = diff_documents(old, new)
    sys.stdout.write(_report(args.format, diffs, args.old, args.new, _use_color(args.color)))
    return 1 if (args.exit_code and diffs) else 0


def cmd_git(args: argparse.Namespace) -> int:
    try:
        files = changed_files(args.range, args.paths or None)
    except GitError as exc:
        print(f"plcdiff: {exc}", file=sys.stderr)
        return 2
    color = _use_color(args.color)
    any_change = False
    parts: list[str] = []
    for f in files:
        try:
            old = loads(f.old, f.old_path, include_values=not args.no_values)
            new = loads(f.new, f.path, include_values=not args.no_values)
        except UnsupportedFormat:
            continue  # an .xml file that is not a PLC export
        diffs = diff_documents(old, new)
        if not diffs:
            continue
        any_change = True
        label_old = f"a/{f.old_path}"
        label_new = f"b/{f.path}"
        parts.append(_report(args.format, diffs, label_old, label_new, color))
    if not parts:
        parts.append(
            "### plcdiff\n\nNo PLC program changes.\n"
            if args.format == "markdown"
            else ("[]\n" if args.format == "json" else "No PLC program changes.\n")
        )
    if args.format == "json" and len(parts) > 1:
        sys.stdout.write("[\n" + ",\n".join(p.strip() for p in parts) + "\n]\n")
    else:
        sys.stdout.write("\n".join(parts))
    return 1 if (args.exit_code and any_change) else 0


def cmd_install(args: argparse.Namespace) -> int:
    try:
        for line in install(global_=args.global_, patterns=tuple(args.pattern or DEFAULT_PATTERNS)):
            print(line)
    except GitError as exc:
        print(f"plcdiff: {exc}", file=sys.stderr)
        return 2
    print("Done. `git diff` and `git log -p` now show PLC exports rung by rung.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="plcdiff",
        description="Readable diffs for PLC program exports (Rockwell L5X, PLCopen XML).",
    )
    p.add_argument("--version", action="version", version=f"plcdiff {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser, formats: bool = True) -> None:
        sp.add_argument(
            "--no-values", action="store_true", help="ignore tag values (only declarations)"
        )
        if formats:
            sp.add_argument("-f", "--format", choices=["text", "markdown", "json"], default="text")
            sp.add_argument("--color", choices=["auto", "always", "never"], default="auto")
            sp.add_argument(
                "--exit-code", action="store_true", help="exit 1 when there are changes"
            )

    sp = sub.add_parser("textconv", help="print a diff-friendly text view (git textconv)")
    sp.add_argument("file")
    common(sp, formats=False)
    sp.set_defaults(func=cmd_textconv)

    sp = sub.add_parser("diff", help="semantic diff of two export files")
    sp.add_argument("old")
    sp.add_argument("new")
    common(sp)
    sp.set_defaults(func=cmd_diff)

    sp = sub.add_parser("git", help="semantic diff of PLC files changed in a git range")
    sp.add_argument("range", nargs="?", help="A..B, A (vs. working tree) or empty (HEAD)")
    sp.add_argument("paths", nargs="*", help="limit to these paths")
    common(sp)
    sp.set_defaults(func=cmd_git)

    sp = sub.add_parser("install", help="register plcdiff as a git diff driver")
    sp.add_argument("--global", dest="global_", action="store_true", help="for all repos")
    sp.add_argument(
        "--pattern",
        action="append",
        help="file pattern to map (repeatable, default *.L5X *.l5x); e.g. 'plc/*.xml'",
    )
    sp.set_defaults(func=cmd_install)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
