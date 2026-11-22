"""Output formats for ``plcdiff diff``: terminal text, Markdown, JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass

from plcdiff.diff import BlockDiff, Change, summarize
from plcdiff.model import Entry

SYMBOL = {"added": "+", "removed": "-", "changed": "~"}


@dataclass
class Style:
    color: bool = False

    def _wrap(self, code: str, s: str) -> str:
        return f"\033[{code}m{s}\033[0m" if self.color else s

    def bold(self, s: str) -> str:
        return self._wrap("1", s)

    def red(self, s: str) -> str:
        return self._wrap("31", s)

    def green(self, s: str) -> str:
        return self._wrap("32", s)

    def yellow(self, s: str) -> str:
        return self._wrap("33", s)

    def dim(self, s: str) -> str:
        return self._wrap("2", s)


def _entry_lines(entry: Entry) -> list[str]:
    lines = [entry.text] if entry.text != "Description" or not entry.note else []
    lines += [f"// {line}" for line in entry.note.splitlines() if line.strip()]
    return lines


def _change_lines(c: Change) -> list[tuple[str, str]]:
    """(sign, text) pairs for one change."""
    out: list[tuple[str, str]] = []
    if c.old is not None:
        out += [("-", line) for line in _entry_lines(c.old)]
    if c.new is not None:
        out += [("+", line) for line in _entry_lines(c.new)]
    if c.op == "changed" and c.old is not None and c.new is not None:
        # Drop lines identical on both sides (e.g. unchanged comment).
        old = [t for s, t in out if s == "-"]
        new = [t for s, t in out if s == "+"]
        if old[1:] == new[1:] and old[:1] != new[:1]:
            out = [("-", old[0]), ("+", new[0])]
        elif old[:1] == new[:1]:
            out = [(" ", old[0])] + [("-", t) for t in old[1:]] + [("+", t) for t in new[1:]]
    return out


def text_report(diffs: list[BlockDiff], old: str, new: str, color: bool = False) -> str:
    st = Style(color)
    out = [st.bold(f"plcdiff {old} -> {new}"), st.dim(summarize(diffs)), ""]
    for d in diffs:
        tag = {"added": " (new)", "removed": " (deleted)", "changed": ""}[d.status]
        out.append(st.bold(d.title + tag))
        for c in d.changes:
            sym = SYMBOL[c.op]
            paint = {"+": st.green, "-": st.red, "~": st.yellow}[sym]
            header = f"  {paint(sym)} {c.name}"
            added, removed = c.instruction_delta()
            if added or removed:
                delta = " ".join(
                    [*(st.green("+" + i) for i in added), *(st.red("-" + i) for i in removed)]
                )
                header += f"   {delta}"
            out.append(header)
            for sign, line in _change_lines(c):
                p = {"+": st.green, "-": st.red, " ": st.dim}[sign]
                out.append("      " + p(f"{sign} {line}"))
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def markdown_report(diffs: list[BlockDiff], old: str, new: str) -> str:
    out = [f"### plcdiff: `{old}` → `{new}`", "", f"**{summarize(diffs)}**", ""]
    for d in diffs:
        tag = {"added": " *(new)*", "removed": " *(deleted)*", "changed": ""}[d.status]
        out.append(f"#### {d.title}{tag}")
        out.append("")
        out.append("```diff")
        for c in d.changes:
            out.append(f"@@ {c.name} ({c.op}) @@")
            out += [f"{sign}{line}" for sign, line in _change_lines(c)]
        out.append("```")
        out.append("")
    return "\n".join(out)


def _entry_json(e: Entry | None) -> dict[str, str] | None:
    if e is None:
        return None
    return {"text": e.text, "note": e.note}


def json_report(diffs: list[BlockDiff], old: str, new: str) -> str:
    payload = {
        "old": old,
        "new": new,
        "summary": summarize(diffs),
        "blocks": [
            {
                "title": d.title,
                "status": d.status,
                "changes": [
                    {
                        "op": c.op,
                        "name": c.name,
                        "old": _entry_json(c.old),
                        "new": _entry_json(c.new),
                    }
                    for c in d.changes
                ],
            }
            for d in diffs
        ],
    }
    return json.dumps(payload, indent=2) + "\n"
