"""Rockwell Automation Studio 5000 / RSLogix 5000 ``.L5X`` exports."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from plcdiff._xml import child, children, local, oneline, text
from plcdiff.model import Block, Document, Entry

ROOT = "RSLogix5000Content"


def description(el: ET.Element) -> str:
    """Description of a tag/member/routine, plain or localized."""
    desc = child(el, "Description")
    if desc is None:
        return ""
    localized = child(desc, "LocalizedDescription")
    return text(localized if localized is not None else desc)


def comment(el: ET.Element) -> str:
    com = child(el, "Comment")
    if com is not None:
        localized = child(com, "LocalizedComment")
        return text(localized if localized is not None else com)
    comments = child(el, "Comments")
    if comments is not None:
        return "\n".join(text(c) for c in comments)
    return ""


def parse(root: ET.Element, include_values: bool = True) -> Document:
    controller = child(root, "Controller")
    if controller is None:
        raise ValueError("L5X file has no <Controller> element")
    name = controller.get("Name", root.get("TargetName", "controller"))
    doc = Document(format="L5X", name=name)
    doc.info = {
        "target": f"{root.get('TargetType', 'Controller')} {root.get('TargetName', name)}",
        "software": root.get("SoftwareRevision", ""),
        "processor": controller.get("ProcessorType", ""),
    }

    ctl = doc.block("Controller", kind="keyed", unit="Property")
    for attr in ("ProcessorType", "MajorRev", "MinorRev", "CommPath"):
        if controller.get(attr):
            ctl.add(f"{attr} = {controller.get(attr)}", key=attr)
    if description(controller):
        ctl.add("Description", key="Description", note=description(controller))
    if not ctl.entries:
        doc.blocks.remove(ctl)

    _datatypes(doc, controller)
    _modules(doc, controller)
    _aois(doc, controller, include_values)
    _tags(doc, child(controller, "Tags"), ("Controller Tags",), include_values)
    _programs(doc, controller, include_values)
    _tasks(doc, controller)
    return doc


def _datatypes(doc: Document, controller: ET.Element) -> None:
    for dt in children(child(controller, "DataTypes"), "DataType"):
        block = doc.block("DataType " + dt.get("Name", "?"), kind="keyed", unit="Member")
        if description(dt):
            block.add("Description", key="", note=description(dt))
        for m in children(child(dt, "Members"), "Member"):
            if m.get("Hidden") == "true":
                continue  # backing SINT for packed BOOLs: noise
            dtype = m.get("DataType", "?")
            if dtype == "BIT":
                dtype = "BOOL"
            dim = m.get("Dimension", "0")
            decl = f"{m.get('Name')} : {dtype}" + (f"[{dim}]" if dim not in ("", "0") else "")
            block.add(decl, key=m.get("Name"), note=description(m))


def _modules(doc: Document, controller: ET.Element) -> None:
    modules = child(controller, "Modules")
    if modules is None:
        return
    block = doc.block("Modules", kind="keyed", unit="Module")
    for mod in children(modules, "Module"):
        parts = [f"{mod.get('Name')} : {mod.get('CatalogNumber', '?')}"]
        if mod.get("Major"):
            parts.append(f"rev {mod.get('Major')}.{mod.get('Minor', '0')}")
        parent = mod.get("ParentModule")
        if parent and parent != mod.get("Name"):
            parts.append(f"parent {parent}")
        addresses = [p.get("Address", "") for p in children(child(mod, "Ports"), "Port")]
        addresses = [a for a in addresses if a]
        if addresses:
            parts.append("address " + ",".join(addresses))
        if mod.get("Inhibited") == "true":
            parts.append("INHIBITED")
        block.add(", ".join(parts), key=mod.get("Name"), note=description(mod))


def _aois(doc: Document, controller: ET.Element, include_values: bool) -> None:
    aois = child(controller, "AddOnInstructionDefinitions")
    if aois is None:
        return
    for aoi in children(aois, "AddOnInstructionDefinition"):
        name = aoi.get("Name", "?")
        head = ("AOI " + name,)
        block = doc.block(*head, "Parameters", kind="keyed", unit="Parameter")
        block.add(f"Revision {aoi.get('Revision', '?')}", key="Revision", note=description(aoi))
        for p in children(child(aoi, "Parameters"), "Parameter"):
            decl = f"{p.get('Name')} : {p.get('DataType')} ({p.get('Usage', '?')})"
            if p.get("Required") == "true":
                decl += " required"
            block.add(decl, key=p.get("Name"), note=description(p))
        local_tags = child(aoi, "LocalTags")
        if local_tags is not None:
            _tags(doc, local_tags, (*head, "Local Tags"), include_values, tag="LocalTag")
        _routines(doc, aoi, head)


def _decl(tag: ET.Element) -> str:
    decl = f"{tag.get('Name')} : {tag.get('DataType', '?')}"
    dim = tag.get("Dimensions") or tag.get("Dimension")
    if dim and dim != "0":
        decl += f"[{dim.replace(' ', ',')}]"
    if tag.get("TagType") == "Alias":
        decl = f"{tag.get('Name')} alias for {tag.get('AliasFor', '?')}"
    elif tag.get("TagType") == "Produced":
        decl += " produced"
    elif tag.get("TagType") == "Consumed":
        decl += " consumed"
    if tag.get("Usage") and tag.get("Usage") not in ("Local", "Public"):
        decl += f" ({tag.get('Usage')})"
    if tag.get("Constant") == "true":
        decl += " constant"
    access = tag.get("ExternalAccess")
    if access and access != "Read/Write":
        decl += f" access={access}"
    return decl


def _tags(
    doc: Document,
    tags: ET.Element | None,
    path: tuple[str, ...],
    include_values: bool,
    tag: str = "Tag",
) -> None:
    if tags is None:
        return
    block = doc.block(*path, kind="keyed", unit="Tag")
    values: Block | None = None
    if include_values:
        values = doc.block(*path[:-1], path[-1] + " (values)", kind="keyed", unit="Value")
    for t in children(tags, tag):
        name = t.get("Name", "?")
        block.add(_decl(t), key=name, note=description(t))
        if values is None:
            continue
        for member_name, value in tag_values(t):
            values.add(f"{member_name} = {value}", key=member_name)
    if values is not None and not values.entries:
        doc.blocks.remove(values)


def tag_values(tag: ET.Element) -> list[tuple[str, str]]:
    """Flatten a tag's ``Decorated`` (or ``String``) data into name/value pairs."""
    name = tag.get("Name", "?")
    datas = list(children(tag, "Data")) + list(children(tag, "DefaultData"))
    for data in datas:
        if data.get("Format") == "Decorated":
            out: list[tuple[str, str]] = []
            for item in data:
                _flatten(item, name, out)
            return out
    for data in datas:
        if data.get("Format") == "String":
            return [(name, text(data))]
    return []


def _flatten(el: ET.Element, prefix: str, out: list[tuple[str, str]]) -> None:
    kind = local(el.tag)
    if kind in ("DataValue", "DataValueMember"):
        here = prefix if kind == "DataValue" else f"{prefix}.{el.get('Name')}"
        value = el.get("Value")
        out.append((here, value if value is not None else text(el)))
    elif kind in ("Structure", "Array"):
        for sub in el:
            _flatten(sub, prefix, out)
    elif kind in ("StructureMember", "ArrayMember"):
        here = f"{prefix}.{el.get('Name')}"
        for sub in el:
            _flatten(sub, here, out)
    elif kind == "Element":
        here = prefix + el.get("Index", "[?]")
        if el.get("Value") is not None:
            out.append((here, el.get("Value", "")))
        for sub in el:
            _flatten(sub, here, out)


def _programs(doc: Document, controller: ET.Element, include_values: bool) -> None:
    programs = child(controller, "Programs")
    if programs is None:
        return
    summary = doc.block("Programs", kind="keyed", unit="Program")
    for prog in children(programs, "Program"):
        name = prog.get("Name", "?")
        line = f"{name} main={prog.get('MainRoutineName', '-')}"
        if prog.get("FaultRoutineName"):
            line += f" fault={prog.get('FaultRoutineName')}"
        if prog.get("Disabled") == "true":
            line += " DISABLED"
        summary.add(line, key=name, note=description(prog))
        head = ("Program " + name,)
        _tags(doc, child(prog, "Tags"), (*head, "Tags"), include_values)
        _routines(doc, prog, head)


def _routines(doc: Document, owner: ET.Element, head: tuple[str, ...]) -> None:
    routines = child(owner, "Routines")
    if routines is None:
        return
    for r in children(routines, "Routine"):
        rtype = r.get("Type", "?")
        title = f"Routine {r.get('Name')} ({rtype})"
        rll = child(r, "RLLContent")
        st = child(r, "STContent")
        if rll is not None:
            block = doc.block(*head, title, kind="sequence", unit="Rung")
            for rung in children(rll, "Rung"):
                logic = oneline(text(child(rung, "Text")))
                rung_type = rung.get("Type", "N")
                if rung_type not in ("N", ""):
                    logic = f"[{rung_type}] {logic}"
                block.add(logic, note=comment(rung))
        elif st is not None:
            block = doc.block(*head, title, kind="sequence", unit="Line")
            for line in children(st, "Line"):
                block.add("".join(line.itertext()).strip("\r\n").rstrip())
        elif child(r, "EncodedData") is not None or child(r, "EncryptedContent") is not None:
            block = doc.block(*head, title, kind="sequence", unit="Line")
            block.add("(source protected)")
        else:
            block = doc.block(*head, title, kind="sequence", unit="Element")
            for content in r:
                if local(content.tag) == "Description":
                    continue
                _generic(content, block)
        if description(r):
            block.entries.insert(0, Entry("Description", note=description(r)))


def _generic(el: ET.Element, block: Block, depth: int = 0) -> None:
    """Graphical content (FBD, SFC): one line per element with its attributes."""
    attrs = " ".join(f'{k}="{v}"' for k, v in sorted(el.attrib.items()))
    body = oneline(el.text or "") if len(el) == 0 else ""
    line = "  " * depth + local(el.tag) + (f" {attrs}" if attrs else "")
    if body:
        line += f": {body}"
    block.add(line)
    for sub in el:
        _generic(sub, block, depth + 1)


def _tasks(doc: Document, controller: ET.Element) -> None:
    tasks = child(controller, "Tasks")
    if tasks is None:
        return
    block = doc.block("Tasks", kind="keyed", unit="Task")
    for task in children(tasks, "Task"):
        parts = [f"{task.get('Name')} : {task.get('Type', '?')}"]
        if task.get("Rate"):
            parts.append(f"rate {task.get('Rate')} ms")
        if task.get("Priority"):
            parts.append(f"priority {task.get('Priority')}")
        if task.get("Watchdog"):
            parts.append(f"watchdog {task.get('Watchdog')} ms")
        if task.get("InhibitTask") == "true":
            parts.append("INHIBITED")
        progs = [
            p.get("Name", "?")
            for p in children(child(task, "ScheduledPrograms"), "ScheduledProgram")
        ]
        parts.append("programs " + (", ".join(progs) if progs else "-"))
        block.add(", ".join(parts), key=task.get("Name"), note=description(task))
