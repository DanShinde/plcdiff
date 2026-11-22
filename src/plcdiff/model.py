"""The normalized, vendor-neutral view of a PLC project.

Every supported export format is parsed into a :class:`Document`: an ordered
list of :class:`Block` objects.  A block is one logical part of the project
(the controller tags, one routine, one data type, ...).  It holds entries that
are either *keyed* (tags, members, parameters: compared by name, order does not
matter) or *sequential* (rungs, Structured Text lines: compared by position).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["keyed", "sequence"]


@dataclass(frozen=True)
class Entry:
    """One line of meaning: a tag declaration, a rung, a line of code."""

    text: str
    key: str | None = None
    note: str = ""
    """Comment or description attached to the entry (may span lines)."""

    def same_as(self, other: Entry) -> bool:
        return self.text == other.text and self.note == other.note


@dataclass
class Block:
    """A titled group of entries, e.g. ``Program MainProgram / Routine Main``."""

    path: tuple[str, ...]
    kind: BlockKind
    entries: list[Entry] = field(default_factory=list)
    unit: str = "Entry"
    """What a single entry is called in reports: Rung, Line, Tag, Member, ..."""

    @property
    def title(self) -> str:
        return " / ".join(self.path)

    def add(self, text: str, key: str | None = None, note: str = "") -> None:
        self.entries.append(Entry(text=text, key=key, note=note.strip()))


@dataclass
class Document:
    """A parsed PLC export."""

    format: str
    name: str
    blocks: list[Block] = field(default_factory=list)
    info: dict[str, str] = field(default_factory=dict)

    def block(self, *path: str, kind: BlockKind = "keyed", unit: str = "Entry") -> Block:
        b = Block(path=tuple(path), kind=kind, unit=unit)
        self.blocks.append(b)
        return b

    def by_title(self) -> dict[str, Block]:
        return {b.title: b for b in self.blocks}
