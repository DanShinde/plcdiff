"""Semantic comparison of two :class:`~plcdiff.model.Document` objects."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Literal

from plcdiff.model import Block, Document, Entry
from plcdiff.render import ordered

Op = Literal["added", "removed", "changed"]

# One ladder instruction with (possibly nested) operands, or a branch marker.
_INSTRUCTION = re.compile(r"[A-Za-z_][\w.:]*\((?:[^()]|\([^()]*\))*\)|[\[\],]")


@dataclass
class Change:
    """One added, removed or changed tag / rung / line."""

    op: Op
    unit: str
    old: Entry | None = None
    new: Entry | None = None
    old_index: int | None = None
    new_index: int | None = None

    @property
    def name(self) -> str:
        entry = self.new or self.old
        if entry is not None and entry.key is not None:
            return f"{self.unit} {entry.key}" if entry.key else "Description"
        base = 0 if self.unit == "Rung" else 1
        if self.new_index is not None and self.old_index is not None:
            if self.old_index != self.new_index:
                return f"{self.unit} {self.new_index + base} (was {self.old_index + base})"
            return f"{self.unit} {self.new_index + base}"
        index = self.new_index if self.new_index is not None else self.old_index
        return f"{self.unit} {(index or 0) + base}"

    def instruction_delta(self) -> tuple[list[str], list[str]]:
        """For changed rungs: instructions that were added and removed."""
        if self.unit != "Rung" or self.old is None or self.new is None:
            return [], []
        a = [t for t in _INSTRUCTION.findall(self.old.text) if t not in "[],"]
        b = [t for t in _INSTRUCTION.findall(self.new.text) if t not in "[],"]
        added: list[str] = []
        removed: list[str] = []
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("replace", "delete"):
                removed += a[i1:i2]
            if tag in ("replace", "insert"):
                added += b[j1:j2]
        return added, removed


@dataclass
class BlockDiff:
    title: str
    status: Literal["added", "removed", "changed"]
    changes: list[Change] = field(default_factory=list)


def _keyed(old: Block | None, new: Block | None, unit: str) -> list[Change]:
    a = {e.key: e for e in (ordered(old) if old else [])}
    b = {e.key: e for e in (ordered(new) if new else [])}
    changes: list[Change] = []
    for key in sorted(a.keys() | b.keys(), key=lambda k: ((k or "").lower(), k or "")):
        ea, eb = a.get(key), b.get(key)
        if ea is None and eb is not None:
            changes.append(Change("added", unit, new=eb))
        elif eb is None and ea is not None:
            changes.append(Change("removed", unit, old=ea))
        elif ea is not None and eb is not None and not ea.same_as(eb):
            changes.append(Change("changed", unit, old=ea, new=eb))
    return changes


def _sequence(old: Block | None, new: Block | None, unit: str) -> list[Change]:
    a = old.entries if old else []
    b = new.entries if new else []
    sm = difflib.SequenceMatcher(
        a=[(e.text, e.note) for e in a], b=[(e.text, e.note) for e in b], autojunk=False
    )
    changes: list[Change] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace":
            paired = min(i2 - i1, j2 - j1)
            for k in range(paired):
                changes.append(Change("changed", unit, a[i1 + k], b[j1 + k], i1 + k, j1 + k))
            for i in range(i1 + paired, i2):
                changes.append(Change("removed", unit, old=a[i], old_index=i))
            for j in range(j1 + paired, j2):
                changes.append(Change("added", unit, new=b[j], new_index=j))
        elif tag == "delete":
            for i in range(i1, i2):
                changes.append(Change("removed", unit, old=a[i], old_index=i))
        elif tag == "insert":
            for j in range(j1, j2):
                changes.append(Change("added", unit, new=b[j], new_index=j))
    return changes


def diff_documents(old: Document, new: Document) -> list[BlockDiff]:
    """Compare two documents block by block, in the order of the new one."""
    a = old.by_title()
    b = new.by_title()
    titles = [blk.title for blk in new.blocks]
    titles += [blk.title for blk in old.blocks if blk.title not in b]
    result: list[BlockDiff] = []
    for title in titles:
        ba, bb = a.get(title), b.get(title)
        ref = bb or ba
        assert ref is not None
        fn = _sequence if ref.kind == "sequence" else _keyed
        changes = fn(ba, bb, ref.unit)
        if not changes:
            continue
        status: Literal["added", "removed", "changed"] = (
            "added" if ba is None else "removed" if bb is None else "changed"
        )
        result.append(BlockDiff(title, status, changes))
    return _drop_values_of_new_tags(result)


_BASE_NAME = re.compile(r"^[^.\[]+")


def _drop_values_of_new_tags(diffs: list[BlockDiff]) -> list[BlockDiff]:
    """A new or deleted tag already says it all; skip its individual values."""
    gone_or_new: dict[str, set[str]] = {}
    for d in diffs:
        for c in d.changes:
            if c.unit == "Tag" and c.op in ("added", "removed"):
                entry = c.new or c.old
                if entry is not None and entry.key:
                    gone_or_new.setdefault(d.title + " (values)", set()).add(entry.key)
    out: list[BlockDiff] = []
    for d in diffs:
        skip = gone_or_new.get(d.title)
        if skip:
            kept = []
            for c in d.changes:
                entry = c.new or c.old
                m = _BASE_NAME.match(entry.key or "") if entry is not None else None
                if c.op != "changed" and m and m.group(0) in skip:
                    continue
                kept.append(c)
            d.changes = kept
        if d.changes:
            out.append(d)
    return out


def summarize(diffs: list[BlockDiff]) -> str:
    """``3 rungs changed, 1 tag added`` style one-liner."""
    if not diffs:
        return "no changes"
    counts: dict[tuple[str, str], int] = {}
    for d in diffs:
        for c in d.changes:
            counts[(c.unit, c.op)] = counts.get((c.unit, c.op), 0) + 1
    parts = []
    for (unit, op), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        noun = unit.lower() + ("s" if n != 1 else "")
        parts.append(f"{n} {noun} {op}")
    return ", ".join(parts)
