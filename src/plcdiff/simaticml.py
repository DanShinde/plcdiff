"""Siemens TIA Portal SimaticML exports (Openness ``Export``, "Export blocks" add-ins, TIA Add-Ins).

One SimaticML file holds one object: a block (OB, FB, FC, global or instance DB), a PLC data
type, or a PLC tag table.  Everything that changes on every export or with the project rather
than the object is left out, so two exports of the same block compare equal:

* ``<Engineering version>`` and ``<DocumentInfo>`` (TIA version, export time, installed products);
* the ``ID`` attributes that number the document's objects in file order;
* ``UId`` numbers inside networks (wiring is resolved to operands instead);
* compile and modification dates, consistency flags and other read-only status nodes;
* interface members TIA adds on its own (``Informative="true"``).

LAD and FBD networks are decoded into one statement per output: ``#Run := #Start AND NOT #Stop``.
SCL networks are compared line by line.  Titles and comments are kept apart from the logic, so a
comment-only edit is reported as such.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator

from plcdiff._xml import child, children, local, oneline
from plcdiff.model import Document

ROOT = "Document"

KINDS = {
    "SW.Blocks.OB": "OB",
    "SW.Blocks.FB": "FB",
    "SW.Blocks.FC": "FC",
    "SW.Blocks.GlobalDB": "DB",
    "SW.Blocks.InstanceDB": "DB",
    "SW.Blocks.ArrayDB": "DB",
    "SW.Types.PlcStruct": "UDT",
    "SW.Tags.PlcTagTable": "Tag table",
}

# Block attributes that change with the project, the export or the compiler, not the source.
VOLATILE = {
    "Interface",
    "Name",
    "Namespace",
    "AutoNumber",
    "CodeModifiedDate",
    "CompileDate",
    "CreationDate",
    "InterfaceModifiedDate",
    "IsConsistent",
    "IsIECCheckEnabled",
    "IsKnowHowProtected",
    "IsWriteProtected",
    "LibraryConformanceStatus",
    "ModifiedDate",
    "ParameterModified",
    "PLCSimAdvancedSupport",
    "StructureModified",
    "InstanceOfNumber",
}

COILS = {
    "Coil": ":=",
    "SCoil": "S",
    "RCoil": "R",
    "NCoil": ":= N",
    "PCoil": ":= P",
    "SetCoil": "S",
    "ResetCoil": "R",
}
COMPARE = {"Eq": "=", "Ne": "<>", "Lt": "<", "Le": "<=", "Gt": ">", "Ge": ">="}
BOOLEAN = {"A": "AND", "O": "OR", "X": "XOR"}


def is_simaticml(root: ET.Element) -> bool:
    return local(root.tag) == ROOT and _object(root) is not None


def _object(root: ET.Element) -> ET.Element | None:
    return next((el for el in root if local(el.tag) in KINDS), None)


def _kids(el: ET.Element | None) -> list[ET.Element]:
    return list(el) if el is not None else []


def _attr(el: ET.Element | None, name: str) -> str:
    found = child(el, "AttributeList", name)
    return (found.text or "").strip() if found is not None else ""


def multilingual(el: ET.Element | None, composition: str) -> str:
    """Text of a ``MultilingualText`` (block/network title or comment), every culture joined."""
    for ml in children(child(el, "ObjectList"), "MultilingualText"):
        if ml.get("CompositionName") != composition:
            continue
        texts = []
        for item in ml.iter():
            if local(item.tag) == "MultilingualTextItem":
                culture = _attr(item, "Culture")
                value = _attr(item, "Text")
                if value:
                    texts.append(value if not culture else f"[{culture}] {value}")
        return (
            "\n".join(texts) if len(texts) > 1 else (texts[0].split("] ", 1)[-1] if texts else "")
        )
    return ""


def parse(root: ET.Element, include_values: bool = True) -> Document:
    obj = _object(root)
    if obj is None:
        raise ValueError("SimaticML file holds no block, data type or tag table")
    kind = KINDS[local(obj.tag)]
    name = _attr(obj, "Name") or "?"
    doc = Document(format="SimaticML", name=name)
    engineering = child(root, "Engineering")
    doc.info = {"target": f"{kind} {name}"}
    if engineering is not None and engineering.get("version"):
        doc.info["software"] = "TIA Portal " + engineering.get("version", "")
    head = f"{kind} {name}"
    if kind == "Tag table":
        _tag_table(doc, obj, head, include_values)
        return doc
    _attributes(doc, obj, head)
    sections = child(obj, "AttributeList", "Interface", "Sections")
    if sections is not None:
        _interface(doc, sections, head, include_values)
    _networks(doc, obj, head)
    return doc


def _attributes(doc: Document, obj: ET.Element, head: str) -> None:
    block = doc.block(head, "Attributes", kind="keyed", unit="Property")
    for el in _kids(child(obj, "AttributeList")):
        tag = local(el.tag)
        if tag in VOLATILE or len(el):
            continue
        value = (el.text or "").strip()
        if value:
            block.add(f"{tag} = {value}", key=tag)
    for composition in ("Title", "Comment"):
        note = multilingual(obj, composition)
        if note:
            block.add(composition, key=composition, note=note)
    if not block.entries:
        doc.blocks.remove(block)


# -- interface / data type members -------------------------------------------


def _members(
    el: ET.Element, prefix: str, section: str
) -> Iterator[tuple[str, str, str, str | None]]:
    """(key, declaration, comment, start value) for every member, nested ones included."""
    for m in children(el, "Member"):
        if m.get("Informative") == "true":
            continue
        name = m.get("Name", "?")
        path = f"{prefix}{name}"
        decl = (
            f"{section} {path} : {m.get('Datatype', '?')}"
            if section
            else f"{path} : {m.get('Datatype', '?')}"
        )
        flags = [a for a in ("Remanence", "Accessibility") if m.get(a)]
        decl += "".join(f" {m.get(a)}" for a in flags)
        start = child(m, "StartValue")
        yield (
            f"{section}.{path}" if section else path,
            decl,
            _comment(m),
            (start.text or "").strip() if start is not None else None,
        )
        nested = child(m, "Sections")
        if nested is not None:
            for sec in children(nested, "Section"):
                yield from _members(sec, path + ".", section)
        yield from _members(m, path + ".", section)
        for sub in children(m, "Subelement"):
            sv = child(sub, "StartValue")
            if sv is not None and (sv.text or "").strip():
                yield (
                    f"{section}.{path}[{sub.get('Path', '?')}]"
                    if section
                    else f"{path}[{sub.get('Path', '?')}]",
                    "",
                    _comment(sub),
                    (sv.text or "").strip(),
                )


def _comment(el: ET.Element) -> str:
    com = child(el, "Comment")
    if com is None:
        return ""
    texts = [
        (t.get("Lang"), "".join(t.itertext()).strip()) for t in children(com, "MultiLanguageText")
    ]
    texts = [(lang, value) for lang, value in texts if value]
    if len(texts) == 1:
        return texts[0][1]
    return "\n".join(f"[{lang}] {value}" for lang, value in texts)


def _interface(doc: Document, sections: ET.Element, head: str, include_values: bool) -> None:
    block = doc.block(head, "Interface", kind="keyed", unit="Member")
    values = doc.block(head, "Interface (values)", kind="keyed", unit="Value")
    for sec in children(sections, "Section"):
        section = sec.get("Name", "")
        for key, decl, note, start in _members(sec, "", section):
            if decl:
                block.add(decl, key=key, note=note)
            if include_values and start is not None and start != "":
                values.add(f"{key.split('.', 1)[-1]} := {start}", key=key)
    if not values.entries:
        doc.blocks.remove(values)
    if not block.entries:
        doc.blocks.remove(block)


# -- tag tables ------------------------------------------------------------------


def _tag_table(doc: Document, obj: ET.Element, head: str, include_values: bool) -> None:
    tags = doc.block(head, kind="keyed", unit="Tag")
    consts = doc.block(head, "User constants", kind="keyed", unit="Constant")
    for el in _kids(child(obj, "ObjectList")):
        tag = local(el.tag)
        name = _attr(el, "Name")
        if tag == "SW.Tags.PlcTag":
            decl = f"{name} : {_attr(el, 'DataTypeName')}"
            address = _attr(el, "LogicalAddress")
            if address:
                decl += f" AT {address}"
            tags.add(decl, key=name, note=multilingual(el, "Comment"))
        elif tag == "SW.Tags.PlcUserConstant":
            decl = f"{name} : {_attr(el, 'DataTypeName')} := {_attr(el, 'Value')}"
            consts.add(decl, key=name, note=multilingual(el, "Comment"))
    for b in (tags, consts):
        if not b.entries:
            doc.blocks.remove(b)


# -- networks --------------------------------------------------------------------


def _networks(doc: Document, obj: ET.Element, head: str) -> None:
    units = [cu for cu in children(child(obj, "ObjectList"), "SW.Blocks.CompileUnit")]
    if not units:
        return
    body = doc.block(head, "Networks", kind="sequence", unit="Line")
    for cu in units:
        lang = _attr(cu, "ProgrammingLanguage") or "?"
        title = multilingual(cu, "Title")
        comment = multilingual(cu, "Comment")
        body.add(f"NETWORK ({lang})", note="\n".join(x for x in (title, comment) if x))
        source = child(cu, "AttributeList", "NetworkSource")
        content = next(iter(source), None) if source is not None else None
        if content is None:
            continue
        kind = local(content.tag)
        if kind == "FlgNet":
            for statement in decode_flgnet(content):
                body.add(statement)
        elif kind == "StructuredText":
            for code, note in scl_lines(content):
                body.add(code, note=note)
        else:
            body.add(f"{kind} network (not decoded)")


def access_text(acc: ET.Element) -> str:
    """An ``<Access>`` as TIA writes it: ``"DB".a.b[1]``, ``#local``, a constant."""
    scope = acc.get("Scope", "")
    const = child(acc, "Constant")
    if const is not None:
        value = child(const, "ConstantValue")
        if value is None:
            value = child(const, "ConstantName")
        text = (value.text or "").strip() if value is not None else const.get("Name", "")
        return ("#" if scope == "LocalConstant" else "") + text
    if scope == "Call":
        info = child(acc, "CallInfo")
        return info.get("Name", "") if info is not None else ""
    symbol = child(acc, "Symbol")
    if symbol is None:
        address = child(acc, "Address")
        return (
            f"%{address.get('Area', '')}{address.get('BitOffset', '')}"
            if address is not None
            else ""
        )
    parts: list[str] = []
    for comp in symbol:
        tag = local(comp.tag)
        if tag == "Component":
            index = [access_text(a) for a in children(comp, "Access")]
            name = comp.get("Name", "")
            if not parts and scope == "GlobalVariable":
                name = f'"{name}"'
            parts.append(name + (f"[{','.join(index)}]" if index else ""))
            sl = comp.get("SliceAccessModifier")
            if sl:
                parts.append("%" + sl.upper())
        elif tag == "Token" and comp.get("Text", "").startswith("%"):
            parts.append(comp.get("Text", ""))
    text = ".".join(parts)
    return "#" + text if scope == "LocalVariable" else text


def _instance(info: ET.Element) -> str:
    inst = child(info, "Instance")
    if inst is None:
        return ""
    names = [c.get("Name", "") for c in inst.iter() if local(c.tag) == "Component"]
    if not names:
        return ""
    text = ".".join(names)
    return f'"{text}"' if inst.get("Scope") == "GlobalVariable" else "#" + text


def _top_level(term: str, op: str) -> bool:
    """True when ``op`` appears in ``term`` outside any parentheses."""
    depth = 0
    for i, ch in enumerate(term):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and term.startswith(op, i):
            return True
    return False


def _and(*items: str) -> str:
    terms = [t for t in items if t and t != "TRUE"]
    if not terms:
        return "TRUE"
    return " AND ".join(
        f"({t})" if _top_level(t, " OR ") or _top_level(t, " XOR ") else t for t in terms
    )


def decode_flgnet(net: ET.Element) -> list[str]:
    """A LAD/FBD network as one statement per coil, box or call, operands resolved."""
    accesses: dict[str, str] = {}
    parts: dict[str, ET.Element] = {}
    order: list[str] = []
    for el in _kids(child(net, "Parts")):
        uid = el.get("UId", "")
        if local(el.tag) == "Access":
            accesses[uid] = access_text(el)
        else:
            parts[uid] = el
            order.append(uid)

    # (uid, pin) -> source: ("rail",), ("ident", text), ("pin", uid, pin), ("open",)
    source: dict[tuple[str, str], tuple[str, ...]] = {}
    targets: dict[tuple[str, str], list[str]] = {}
    for wire in children(child(net, "Wires"), "Wire"):
        cons = list(wire)
        if not cons:
            continue
        first = cons[0]
        kind = local(first.tag)
        if kind == "Powerrail":
            src: tuple[str, ...] = ("rail",)
        elif kind == "IdentCon":
            src = ("ident", accesses.get(first.get("UId", ""), "?"))
        elif kind == "NameCon":
            src = ("pin", first.get("UId", ""), first.get("Name", ""))
        else:
            src = ("open",)
        for con in cons[1:]:
            ckind = local(con.tag)
            if ckind == "NameCon":
                source[(con.get("UId", ""), con.get("Name", ""))] = src
            elif ckind == "IdentCon" and src[0] == "pin":
                targets.setdefault((src[1], src[2]), []).append(
                    accesses.get(con.get("UId", ""), "?")
                )

    def negated(uid: str, pin: str) -> bool:
        return any(n.get("Name") == pin for n in children(parts.get(uid), "Negated"))

    def operand(uid: str) -> str:
        src = source.get((uid, "operand"))
        return src[1] if src and src[0] == "ident" else "?"

    seen: set[tuple[str, str]] = set()

    def value_in(uid: str, pin: str) -> str:
        src = source.get((uid, pin))
        if src is None or src[0] == "open":
            return ""
        if src[0] == "rail":
            text = "TRUE"
        elif src[0] == "ident":
            text = src[1]
        else:
            text = value_out(src[1], src[2])
        if negated(uid, pin):
            text = f"NOT ({text})" if " " in text else f"NOT {text}"
        return text

    def value_out(uid: str, pin: str) -> str:
        part = parts.get(uid)
        if part is None:
            return "?"
        name = part.get("Name", "")
        if (uid, pin) in seen:
            return f"{name}.{pin}"
        seen.add((uid, pin))
        try:
            if name in ("Contact", "PContact", "NContact"):
                op = operand(uid)
                if name != "Contact":
                    op = f"{name[0]}({op})"
                elif negated(uid, "operand"):
                    op = f"NOT {op}"
                return _and(value_in(uid, "in"), op)
            if name in BOOLEAN:
                ins = [value_in(uid, p) for p in _pins(part, "in")]
                ins = [i for i in ins if i]
                if name == "A":
                    return _and(*ins)
                return f" {BOOLEAN[name]} ".join(ins)
            if name in COMPARE:
                cmp = f"{value_in(uid, 'in1')} {COMPARE[name]} {value_in(uid, 'in2')}"
                return _and(value_in(uid, "pre"), cmp)
            if name in ("NegatedContact", "Not"):
                return f"NOT ({value_in(uid, 'in')})"
            if name in COILS and pin == "out":
                return value_in(uid, "in")
            label = _label(part, uid, operand)
            return f"{label}.{pin.upper() if pin in ('eno', 'out', 'q') else pin}"
        finally:
            seen.discard((uid, pin))

    def box(part: ET.Element, uid: str) -> str:
        label = _label(part, uid, operand)
        names: list[str] = []
        if local(part.tag) == "Call":
            names = [p.get("Name", "") for p in children(child(part, "CallInfo"), "Parameter")]
        else:
            types = [
                (tv.text or "").strip()
                for tv in children(part, "TemplateValue")
                if tv.get("Type") == "Type"
            ]
            if types:
                head, _, rest = label.partition(" ")
                label = f"{head}<{','.join(types)}>" + (f" {rest}" if rest else "")
        pins: list[str] = []
        en = value_in(uid, "en")
        if en and en != "TRUE":
            pins.append(f"EN := {en}")
        wired = sorted({p for (u, p) in source if u == uid and p != "en"} - set(names))
        for pin in names + wired:
            value = value_in(uid, pin)
            if value:
                pins.append(f"{pin} := {value}")
        for pin in sorted(p for (u, p) in targets if u == uid):
            pins.append(f"{pin} => {', '.join(targets[(uid, pin)])}")
        return f"{label}({', '.join(pins)})"

    statements: list[str] = []
    for uid in order:
        part = parts[uid]
        name = part.get("Name", "") if local(part.tag) == "Part" else ""
        if name in COILS:
            op = operand(uid)
            cond = value_in(uid, "in")
            if COILS[name] == ":=":
                statements.append(f"{'NOT ' if negated(uid, 'operand') else ''}{op} := {cond}")
            else:
                statements.append(f"{COILS[name]} {op} IF {cond}")
        elif name in ("Contact", "PContact", "NContact", "O", "A", "X", "Not", *COMPARE):
            continue  # folded into the statements that use them
        else:
            statements.append(box(part, uid))
    return statements


def _pins(part: ET.Element, prefix: str) -> list[str]:
    card = 2
    for tv in children(part, "TemplateValue"):
        if tv.get("Name") == "Card" and (tv.text or "").strip().isdigit():
            card = int((tv.text or "").strip())
    return [f"{prefix}{i}" for i in range(1, card + 1)]


def _label(part: ET.Element, uid: str, operand: Callable[[str], str]) -> str:
    if local(part.tag) == "Call":
        info = child(part, "CallInfo")
        if info is None:
            return "CALL ?"
        inst = _instance(info)
        name = f'"{info.get("Name", "?")}"'
        return f"{name} {inst}" if inst else name
    name = part.get("Name", "?")
    instance = _instance(part)
    if instance:
        return f"{name} {instance}"
    if any(local(c.tag) == "Negated" for c in part) or name in ("TON", "TOF", "TP", "SR", "RS"):
        op = operand(uid)
        if op != "?":
            return f"{name} {op}"
    return name


# -- SCL ---------------------------------------------------------------------------


def scl_lines(st: ET.Element) -> list[tuple[str, str]]:
    """SCL code as (code, comment) lines; blank lines dropped, indentation kept."""
    lines: list[tuple[list[str], list[str]]] = [([], [])]

    def emit(text: str) -> None:
        lines[-1][0].append(text)

    def walk(el: ET.Element) -> None:
        for c in el:
            tag = local(c.tag)
            if tag == "Token":
                emit(c.get("Text", ""))
            elif tag == "Blank":
                emit(" " * int(c.get("Num", "1") or 1))
            elif tag == "NewLine":
                for _ in range(int(c.get("Num", "1") or 1)):
                    lines.append(([], []))
            elif tag in ("LineComment", "Comment"):
                text = oneline("".join(t.text or "" for t in c.iter() if local(t.tag) == "Text"))
                lines[-1][1].append(text)
            elif tag == "Access":
                if c.get("Scope") == "Call":
                    info = child(c, "CallInfo")
                    instr = child(c, "Instruction")
                    if instr is not None:
                        emit(instr.get("Name", ""))
                        walk(instr)
                    elif info is not None:
                        emit(_instance(info) or f'"{info.get("Name", "")}"')
                        walk(info)
                else:
                    emit(access_text(c))
            elif tag == "Parameter":
                emit(c.get("Name", ""))
                walk(c)
            elif tag in ("Instance", "Symbol", "Constant"):
                continue
            elif tag == "Text":
                emit(c.text or "")
            else:
                walk(c)

    walk(st)
    out = []
    for code, notes in lines:
        text = "".join(code).rstrip()
        note = " ".join(n for n in notes if n)
        if text.strip() or note:
            out.append((text, note))
    return out
