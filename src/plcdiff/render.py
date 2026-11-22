"""Plain-text rendering used as a git ``textconv`` filter."""

from __future__ import annotations

from plcdiff.model import Block, Document, Entry


def sort_key(entry: Entry) -> tuple[str, str]:
    return ((entry.key or "").lower(), entry.key or "")


def ordered(block: Block) -> list[Entry]:
    """Keyed blocks are sorted by name so a reordered export diffs clean."""
    if block.kind == "keyed":
        return sorted(block.entries, key=sort_key)
    return list(block.entries)


def render_entry(entry: Entry) -> list[str]:
    lines = [entry.text]
    lines += [f"    // {line}" for line in entry.note.splitlines() if line.strip()]
    return lines


def render(doc: Document) -> str:
    """One line per tag, rung or code line; stable and friendly to ``diff``."""
    out = [f"# {doc.format}: {doc.name}"]
    for key, value in doc.info.items():
        if value:
            out.append(f"# {key}: {value}")
    for block in doc.blocks:
        out.append("")
        out.append(f"== {block.title} ==")
        for entry in ordered(block):
            out.extend(render_entry(entry))
    return "\n".join(out) + "\n"
