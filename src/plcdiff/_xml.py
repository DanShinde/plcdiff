"""Small ElementTree helpers shared by the format parsers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Iterator


def local(tag: str) -> str:
    """Strip an ``{namespace}`` prefix from an element tag."""
    return tag.rsplit("}", 1)[-1]


def children(el: ET.Element | None, name: str) -> Iterator[ET.Element]:
    if el is None:
        return
    for child in el:
        if local(child.tag) == name:
            yield child


def child(el: ET.Element | None, *names: str) -> ET.Element | None:
    """Follow a path of child names, ignoring namespaces."""
    cur = el
    for name in names:
        if cur is None:
            return None
        cur = next(children(cur, name), None)
    return cur


def text(el: ET.Element | None) -> str:
    """All text inside an element, with surrounding whitespace removed."""
    if el is None:
        return ""
    return "".join(el.itertext()).strip()


def oneline(value: str) -> str:
    """Collapse whitespace so free text fits on one diff line."""
    return " ".join(value.split())
