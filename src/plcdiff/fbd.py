"""Rockwell FBD sheets (``<FBDContent>`` in an ``.L5X``) -> one statement per output.

A sheet is nodes joined by wires.  Positions on the sheet are layout, not logic, so they are
left out; instead every output is written as the expression wired into it:

* an output reference (``ORef``): ``Run := (Start OR Run) AND NOT Stop``;
* every other block, function, Add-On Instruction or ``JSR``: a call with each wired pin,
  ``TONR JamTimer(TimerEnable := Running AND PhotoEye, PRE := 5000, DN => Jam)``.

Boolean blocks (``BAND``/``BOR``/``BXOR``/``BNOT``) and comparisons (``EQU``, ``GRT``, ...) are
folded into the expressions that read them.  Connectors (``OCon``/``ICon``) carry a signal across
the sheet by name.  A feedback loop is cut at the block's output member.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from plcdiff._xml import local, oneline, text

BOOLEAN = {
    "BAND": "AND",
    "AND": "AND",
    "BOR": "OR",
    "OR": "OR",
    "BXOR": "XOR",
    "XOR": "XOR",
    "BNOT": "NOT",
    "NOT": "NOT",
}
COMPARE = {"EQU": "=", "NEQ": "<>", "LES": "<", "LEQ": "<=", "GRT": ">", "GEQ": ">="}
NODES = {
    "IRef",
    "ORef",
    "ICon",
    "OCon",
    "Block",
    "Function",
    "AddOnInstruction",
    "JSR",
    "SBR",
    "RET",
}


def _wrap(term: str) -> str:
    """Parenthesize a term that has a top-level AND / OR / XOR."""
    depth = 0
    for i, ch in enumerate(term):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and any(term.startswith(op, i) for op in (" AND ", " OR ", " XOR ")):
            return f"({term})"
    return term


class Sheet:
    def __init__(self, sheet: ET.Element) -> None:
        self.nodes: dict[str, ET.Element] = {}
        self.order: list[str] = []
        self.into: dict[tuple[str, str], tuple[str, str]] = {}
        self.outof: dict[tuple[str, str], list[str]] = {}
        self.connectors: dict[str, tuple[str, str]] = {}
        self.notes: list[str] = []
        wires: list[ET.Element] = []
        for el in sheet:
            tag = local(el.tag)
            if tag == "Wire":
                wires.append(el)
            elif tag == "TextBox":
                note = oneline(text(el))
                if note:
                    self.notes.append(note)
            elif tag in NODES and el.get("ID") is not None:
                self.nodes[el.get("ID", "")] = el
                self.order.append(el.get("ID", ""))
        for w in wires:
            src = (w.get("FromID", ""), w.get("FromParam", ""))
            dst = (w.get("ToID", ""), w.get("ToParam", ""))
            self.into.setdefault(dst, src)
            self.outof.setdefault(src, []).append(dst[0])
            node = self.nodes.get(dst[0])
            if node is not None and local(node.tag) == "ICon":
                self.connectors[node.get("Name", "")] = src
        self._walking: set[tuple[str, str]] = set()

    # -- expressions --------------------------------------------------------------

    def _type(self, node: ET.Element) -> str:
        return (node.get("Type") or node.get("Name") or local(node.tag)).upper()

    def _label(self, node: ET.Element) -> str:
        tag = local(node.tag)
        if tag == "AddOnInstruction":
            name = node.get("Name", "?")
        elif tag == "JSR":
            return f"JSR {node.get('Routine', '?')}"
        else:
            name = node.get("Type", tag)
        operand = node.get("Operand")
        return f"{name} {operand}" if operand else name

    def feeding(self, nid: str, pin: str) -> str | None:
        src = self.into.get((nid, pin))
        if src is None and pin in ("In", "In1", "Source"):
            src = self.into.get((nid, ""))
        return None if src is None else self.expr(*src)

    def expr(self, nid: str, pin: str) -> str:
        node = self.nodes.get(nid)
        if node is None:
            return "?"
        tag, typ = local(node.tag), self._type(node)
        if tag == "IRef":
            return node.get("Operand", "?")
        if tag == "OCon":
            src = self.connectors.get(node.get("Name", ""))
            if src is None or (nid, pin) in self._walking:
                return node.get("Name", "?")
            self._walking.add((nid, pin))
            try:
                return self.expr(*src)
            finally:
                self._walking.discard((nid, pin))
        key = (nid, pin)
        member = f"{node.get('Operand') or typ}.{pin or 'Out'}"
        if key in self._walking:
            return member  # feedback loop: the block's own output member
        self._walking.add(key)
        try:
            if typ in BOOLEAN and tag in ("Block", "Function"):
                ins = [self.feeding(nid, f"In{i}") for i in range(1, 9)] + [self.feeding(nid, "In")]
                terms = [t for t in ins if t is not None]
                if BOOLEAN[typ] == "NOT":
                    return f"NOT {_wrap(terms[0])}" if terms else "NOT ?"
                return f" {BOOLEAN[typ]} ".join(_wrap(t) for t in terms) or "?"
            if typ in COMPARE and tag in ("Block", "Function"):
                a = self.feeding(nid, "SourceA") or "?"
                b = self.feeding(nid, "SourceB") or "?"
                return f"{a} {COMPARE[typ]} {b}"
            if tag == "Function" and not node.get("Operand"):
                args = [self.feeding(nid, p) for p in self.pins(nid)]
                return f"{typ}({', '.join(a for a in args if a is not None)})"
            return member
        finally:
            self._walking.discard(key)

    def pins(self, nid: str) -> list[str]:
        """Wired input pins of a node, in the order the wires were drawn."""
        return [pin for (to, pin) in self.into if to == nid]

    # -- statements -----------------------------------------------------------------

    def _folded(self, node: ET.Element) -> bool:
        tag, typ = local(node.tag), self._type(node)
        if tag in ("IRef", "ORef", "ICon", "OCon"):
            return True
        if tag in ("Block", "Function") and (typ in BOOLEAN or typ in COMPARE):
            return True
        return tag == "Function" and not node.get("Operand")

    def statements(self) -> list[str]:
        out: list[str] = []
        for nid in self.order:
            node = self.nodes[nid]
            tag = local(node.tag)
            if tag == "ORef":
                src = self.into.get((nid, "")) or self.into.get((nid, "In"))
                if src is None:
                    continue
                feeder = self.nodes.get(src[0])
                if feeder is not None and not self._folded(feeder):
                    continue  # written by that call's own statement as an output pin
                out.append(f"{node.get('Operand', '?')} := {self.expr(*src)}")
            elif not self._folded(node):
                out.append(self._call(nid, node))
        return out

    def _call(self, nid: str, node: ET.Element) -> str:
        args: list[str] = []
        for pin in self.pins(nid):
            value = self.feeding(nid, pin)
            if value is not None:
                args.append(f"{pin or 'In'} := {value}")
        outs: dict[str, list[str]] = {}
        for (src, pin), targets in self.outof.items():
            if src != nid:
                continue
            for t in targets:
                target = self.nodes.get(t)
                if target is not None and local(target.tag) == "ORef":
                    outs.setdefault(pin or "Out", []).append(target.get("Operand", "?"))
        for pin in sorted(outs):
            args.append(f"{pin} => {', '.join(outs[pin])}")
        if local(node.tag) == "JSR":
            for attr in ("In", "Ret"):
                if node.get(attr):
                    args.append(f"{attr} {node.get(attr)}")
        return f"{self._label(node)}({', '.join(args)})"


def decode(fbd: ET.Element) -> list[tuple[str, str]]:
    """(text, note) lines for an ``<FBDContent>``: a ``SHEET n`` header, then its statements."""
    out: list[tuple[str, str]] = []
    for sheet_el in fbd:
        if local(sheet_el.tag) != "Sheet":
            continue
        sheet = Sheet(sheet_el)
        out.append((f"SHEET {sheet_el.get('Number', '?')}", "\n".join(sheet.notes)))
        out += [(s, "") for s in sheet.statements()]
    return out
