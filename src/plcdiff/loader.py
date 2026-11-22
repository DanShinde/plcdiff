"""Detect the export format and parse it into a :class:`~plcdiff.model.Document`."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from plcdiff import l5x, plcopen
from plcdiff._xml import local
from plcdiff.model import Document

SUFFIXES = (".l5x", ".xml", ".plcopen")


class UnsupportedFormat(ValueError):
    """The file is not a PLC export plcdiff understands."""


def loads(data: bytes | str, name: str = "<data>", include_values: bool = True) -> Document:
    """Parse export content.  Raises :class:`UnsupportedFormat` for anything else."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not data.strip():
        return Document(format="empty", name=name)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise UnsupportedFormat(f"{name}: not well-formed XML ({exc})") from exc
    if local(root.tag) == l5x.ROOT:
        return l5x.parse(root, include_values)
    if plcopen.is_plcopen(root):
        return plcopen.parse(root, include_values)
    raise UnsupportedFormat(f"{name}: unknown root element <{local(root.tag)}>")


def load(path: str | Path, include_values: bool = True) -> Document:
    """Parse an export file from disk."""
    p = Path(path)
    return loads(p.read_bytes(), name=str(p), include_values=include_values)


def looks_supported(path: str) -> bool:
    return path.lower().endswith(SUFFIXES)
