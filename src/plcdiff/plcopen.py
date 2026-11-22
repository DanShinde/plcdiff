"""PLCopen TC6 XML (IEC 61131-3) exports: CODESYS, TwinCAT, Beremiz, Machine Expert, ..."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from plcdiff._xml import child, children, local, oneline, text
from plcdiff.model import Block, Document

ROOT = "project"
NAMESPACE_HINT = "plcopen.org/xml/tc6"

VAR_SECTIONS = {
    "inputVars": "VAR_INPUT",
    "outputVars": "VAR_OUTPUT",
    "inOutVars": "VAR_IN_OUT",
    "localVars": "VAR",
    "tempVars": "VAR_TEMP",
    "externalVars": "VAR_EXTERNAL",
    "globalVars": "VAR_GLOBAL",
    "accessVars": "VAR_ACCESS",
}

# Layout-only elements of graphical languages: they change when someone drags a
# box around, not when the logic changes.
LAYOUT = {"position", "relPosition", "connectionPointIn", "connectionPointOut", "addData"}
LAYOUT_ATTRS = {"localId", "height", "width", "executionOrderId", "refLocalId"}


def is_plcopen(root: ET.Element) -> bool:
    return local(root.tag) == ROOT and NAMESPACE_HINT in root.tag


def documentation(el: ET.Element) -> str:
    return text(child(el, "documentation"))


def type_str(type_el: ET.Element | None) -> str:
    """Render a ``<type>``/``<baseType>`` element as IEC 61131-3 text."""
    if type_el is None:
        return "?"
    inner = next(iter(type_el), None)
    if inner is None:
        return "?"
    kind = local(inner.tag)
    if kind == "derived":
        return inner.get("name", "?")
    if kind in ("string", "wstring"):
        length = inner.get("length")
        return kind.upper() + (f"({length})" if length else "")
    if kind == "array":
        dims = ",".join(
            f"{d.get('lower', '?')}..{d.get('upper', '?')}" for d in children(inner, "dimension")
        )
        return f"ARRAY[{dims}] OF {type_str(child(inner, 'baseType'))}"
    if kind == "pointer":
        return f"POINTER TO {type_str(child(inner, 'baseType'))}"
    if kind in ("subrangeSigned", "subrangeUnsigned"):
        rng = child(inner, "range")
        bounds = f"{rng.get('lower')}..{rng.get('upper')}" if rng is not None else "?"
        return f"{type_str(child(inner, 'baseType'))}({bounds})"
    if kind == "enum":
        names = [v.get("name", "?") for v in children(child(inner, "values"), "value")]
        return "(" + ", ".join(names) + ")"
    if kind == "struct":
        return "STRUCT"
    return kind.upper()


def value_str(el: ET.Element | None) -> str:
    """Render an ``<initialValue>`` element."""
    if el is None:
        return ""
    inner = next(iter(el), None)
    if inner is None:
        return ""
    kind = local(inner.tag)
    if kind == "simpleValue":
        return inner.get("value", "")
    if kind == "arrayValue":
        parts = []
        for v in children(inner, "value"):
            item = value_str(v)
            if v.get("repetitionValue"):
                item = f"{v.get('repetitionValue')}({item})"
            parts.append(item)
        return "[" + ", ".join(parts) + "]"
    if kind == "structValue":
        return (
            "("
            + ", ".join(f"{v.get('member')} := {value_str(v)}" for v in children(inner, "value"))
            + ")"
        )
    return oneline(text(inner))


def variable_decl(var: ET.Element) -> str:
    decl = f"{var.get('name')} : {type_str(child(var, 'type'))}"
    if var.get("address"):
        decl = f"{var.get('name')} AT {var.get('address')} : {type_str(child(var, 'type'))}"
    init = value_str(child(var, "initialValue"))
    if init:
        decl += f" := {init}"
    return decl


def parse(root: ET.Element, include_values: bool = True) -> Document:
    header = child(root, "contentHeader")
    file_header = child(root, "fileHeader")
    name = header.get("name", "project") if header is not None else "project"
    doc = Document(format="PLCopen XML", name=name)
    if file_header is not None:
        doc.info = {
            "product": " ".join(
                x for x in (file_header.get("productName"), file_header.get("productVersion")) if x
            ),
            "company": file_header.get("companyName", ""),
        }
    types = child(root, "types")
    if types is not None:
        _datatypes(doc, child(types, "dataTypes"))
        _pous(doc, child(types, "pous"))
    _instances(doc, child(root, "instances", "configurations"))
    # CODESYS keeps global variable lists in vendor data, not in a configuration.
    for gvl in _in_add_data(root, "globalVars"):
        _var_list(doc, gvl, (f"GVL {gvl.get('name', '?')}",))
    doc.blocks = [b for b in doc.blocks if b.entries]
    return doc


def _in_add_data(el: ET.Element, name: str) -> list[ET.Element]:
    """Elements called ``name`` inside an element's own ``<addData>``."""
    found: list[ET.Element] = []
    for add in children(el, "addData"):
        found += [d for d in add.iter() if local(d.tag) == name]
    return found


def _var_list(doc: Document, var_list: ET.Element, path: tuple[str, ...]) -> None:
    block = doc.block(*path, kind="keyed", unit="Variable")
    flags = [f.upper() for f in ("constant", "retain", "persistent") if var_list.get(f) == "true"]
    label = " ".join(["VAR_GLOBAL", *flags])
    for var in children(var_list, "variable"):
        block.add(f"{label} {variable_decl(var)}", key=var.get("name"), note=documentation(var))


def _datatypes(doc: Document, datatypes: ET.Element | None) -> None:
    if datatypes is None:
        return
    for dt in children(datatypes, "dataType"):
        name = dt.get("name", "?")
        base = child(dt, "baseType")
        inner = next(iter(base), None) if base is not None else None
        block = doc.block("DataType " + name, kind="keyed", unit="Member")
        if documentation(dt):
            block.add("Description", key="", note=documentation(dt))
        if inner is not None and local(inner.tag) == "struct":
            for var in children(inner, "variable"):
                block.add(variable_decl(var), key=var.get("name"), note=documentation(var))
        elif inner is not None and local(inner.tag) == "enum":
            for v in children(child(inner, "values"), "value"):
                val = f" := {v.get('value')}" if v.get("value") else ""
                block.add(f"{v.get('name')}{val}", key=v.get("name"))
        else:
            init = value_str(child(dt, "initialValue"))
            block.add(f"{name} : {type_str(base)}" + (f" := {init}" if init else ""), key="(type)")


def _var_sections(doc: Document, iface: ET.Element | None, path: tuple[str, ...]) -> None:
    if iface is None:
        return
    block = doc.block(*path, "Interface", kind="keyed", unit="Variable")
    ret = child(iface, "returnType")
    if ret is not None:
        block.add(f"RETURN : {type_str(ret)}", key="(return)")
    for section in iface:
        kind = VAR_SECTIONS.get(local(section.tag))
        if kind is None:
            continue
        flags = [f for f in ("constant", "retain", "persistent") if section.get(f) == "true"]
        label = " ".join([kind, *(f.upper() for f in flags)])
        for var in children(section, "variable"):
            block.add(f"{label} {variable_decl(var)}", key=var.get("name"), note=documentation(var))


def _body(doc: Document, body: ET.Element | None, path: tuple[str, ...]) -> None:
    if body is None:
        return
    lang_el = next((el for el in body if local(el.tag) != "documentation"), None)
    if lang_el is None:
        return
    lang = local(lang_el.tag)
    title = (*path[:-1], f"{path[-1]} ({lang})")
    if lang in ("ST", "IL"):
        block = doc.block(*title, kind="sequence", unit="Line")
        holder = child(lang_el, "xhtml")
        source = "".join((holder if holder is not None else lang_el).itertext())
        source = source.strip("\r\n")
        for line in source.splitlines():
            block.add(line.rstrip())
    else:
        block = doc.block(*title, kind="sequence", unit="Element")
        _graphical(lang_el, block)


def _graphical(lang_el: ET.Element, block: Block) -> None:
    """LD / FBD / SFC: one line per element, without layout noise."""
    for el in lang_el:
        kind = local(el.tag)
        if kind in LAYOUT:
            continue
        attrs = " ".join(
            f'{k}="{v}"' for k, v in sorted(el.attrib.items()) if k not in LAYOUT_ATTRS
        )
        parts = [kind + (f" {attrs}" if attrs else "")]
        var = child(el, "variable")
        expr = child(el, "expression")
        if var is not None:
            parts.append(oneline(text(var)))
        elif expr is not None:
            parts.append(oneline(text(expr)))
        elif kind == "comment":
            parts.append(oneline(text(child(el, "content"))))
        elif kind == "block":
            for section in ("inputVariables", "inOutVariables", "outputVariables"):
                names = [
                    v.get("formalParameter", "?") for v in children(child(el, section), "variable")
                ]
                if names:
                    parts.append(f"{section[:-9]}({', '.join(names)})")
        elif kind in ("step", "transition", "jumpStep", "actionBlock"):
            cond = child(el, "condition")
            if cond is not None:
                parts.append(oneline(text(cond)))
            for action in children(el, "action"):
                ref = child(action, "reference")
                parts.append(
                    f"{action.get('qualifier', 'N')} "
                    + (ref.get("name", "?") if ref is not None else oneline(text(action)))
                )
        block.add(": ".join(parts) if len(parts) == 2 else " ".join(parts))


def _pous(doc: Document, pous: ET.Element | None) -> None:
    if pous is None:
        return
    summary = doc.block("POUs", kind="keyed", unit="POU")
    for pou in children(pous, "pou"):
        name = pou.get("name", "?")
        ptype = pou.get("pouType", "?")
        summary.add(f"{name} : {ptype}", key=name, note=documentation(pou))
        head = (f"POU {name}",)
        _var_sections(doc, child(pou, "interface"), head)
        _body(doc, child(pou, "body"), (*head, "Body"))
        for action in children(child(pou, "actions"), "action"):
            _body(doc, child(action, "body"), (*head, f"Action {action.get('name')}"))
        for trans in children(child(pou, "transitions"), "transition"):
            _body(doc, child(trans, "body"), (*head, f"Transition {trans.get('name')}"))
        for method in _in_add_data(pou, "method"):
            mhead = (*head, f"Method {method.get('name')}")
            _var_sections(doc, child(method, "interface"), mhead)
            _body(doc, child(method, "body"), (*mhead, "Body"))


def _instances(doc: Document, configurations: ET.Element | None) -> None:
    if configurations is None:
        return
    for conf in children(configurations, "configuration"):
        head = (f"Configuration {conf.get('name')}",)
        _var_sections(doc, conf, head)
        for res in children(conf, "resource"):
            rhead = (*head, f"Resource {res.get('name')}")
            _var_sections(doc, res, rhead)
            block = doc.block(*rhead, "Tasks", kind="keyed", unit="Task")
            for task in children(res, "task"):
                parts = [f"{task.get('name')}"]
                for attr in ("interval", "priority", "single"):
                    if task.get(attr):
                        parts.append(f"{attr} {task.get(attr)}")
                instances = [
                    f"{i.get('name')}:{i.get('typeName')}" for i in children(task, "pouInstance")
                ]
                parts.append("runs " + (", ".join(instances) if instances else "-"))
                block.add(", ".join(parts), key=task.get("name"))
            for inst in children(res, "pouInstance"):
                block.add(
                    f"{inst.get('name')} : {inst.get('typeName')} (no task)",
                    key="inst:" + inst.get("name", "?"),
                )
            if not block.entries:
                doc.blocks.remove(block)
