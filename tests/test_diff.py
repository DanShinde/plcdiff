from __future__ import annotations

import json
from pathlib import Path

from conftest import l5x

from plcdiff import diff_documents, load, loads
from plcdiff.diff import Change, summarize
from plcdiff.model import Entry
from plcdiff.report import json_report, markdown_report, text_report


def _rungs(*rungs: str) -> str:
    inner = "".join(
        f'<Rung Number="{i}" Type="N"><Text><![CDATA[{r}]]></Text></Rung>'
        for i, r in enumerate(rungs)
    )
    return l5x(
        '<Programs><Program Name="P"><Routines><Routine Name="R" Type="RLL"><RLLContent>'
        f"{inner}</RLLContent></Routine></Routines></Program></Programs>"
    )


def test_identical_files_have_no_changes(examples: Path) -> None:
    a = load(examples / "conveyor_v1.L5X")
    assert diff_documents(a, a) == []
    assert summarize([]) == "no changes"


def test_example_l5x_changes(examples: Path) -> None:
    diffs = diff_documents(load(examples / "conveyor_v1.L5X"), load(examples / "conveyor_v2.L5X"))
    by = {d.title: d for d in diffs}
    assert set(by) == {
        "Controller Tags",
        "Controller Tags (values)",
        "Program MainProgram / Routine MainRoutine (RLL)",
        "Program MainProgram / Routine SpeedCalc (ST)",
    }
    tags = by["Controller Tags"].changes
    assert [(c.op, c.name) for c in tags] == [("added", "Tag EStop"), ("added", "Tag Horn")]
    values = by["Controller Tags (values)"].changes
    # The new tag Horn's own value is not repeated as a separate change.
    assert [c.name for c in values] == ["Value Conveyor1.Speed", "Value JamDelay.PRE"]
    rungs = by["Program MainProgram / Routine MainRoutine (RLL)"].changes
    assert [(c.op, c.name) for c in rungs] == [
        ("changed", "Rung 0"),
        ("changed", "Rung 2"),
        ("added", "Rung 4"),
    ]
    assert rungs[0].instruction_delta() == (["XIO(EStop)"], [])


def test_inserted_rung_does_not_renumber_the_rest() -> None:
    old = loads(_rungs("XIC(A)OTE(B);", "XIC(C)OTE(D);", "XIC(E)OTE(F);"))
    new = loads(_rungs("XIC(A)OTE(B);", "NOP();", "XIC(C)OTE(D);", "XIC(E)OTE(F);"))
    (d,) = diff_documents(old, new)
    assert [(c.op, c.name) for c in d.changes] == [("added", "Rung 1")]


def test_changed_rung_after_insert_shows_old_number() -> None:
    old = loads(_rungs("XIC(A)OTE(B);", "XIC(C)OTE(D);"))
    new = loads(_rungs("NOP();", "XIC(A)OTE(B);", "XIC(C)XIO(X)OTE(D);"))
    (d,) = diff_documents(old, new)
    assert [c.name for c in d.changes] == ["Rung 0", "Rung 2 (was 1)"]


def test_removed_rung_and_block() -> None:
    old = loads(_rungs("XIC(A)OTE(B);", "XIC(C)OTE(D);"))
    new = loads(_rungs("XIC(A)OTE(B);"))
    (d,) = diff_documents(old, new)
    assert [(c.op, c.name) for c in d.changes] == [("removed", "Rung 1")]
    gone = diff_documents(old, loads(l5x("")))
    assert {d.status for d in gone} == {"removed"}


def test_instruction_delta_with_nested_operands() -> None:
    c = Change(
        "changed",
        "Rung",
        Entry("XIC(A)MOV(Arr[Idx[0]],B)OTE(C);"),
        Entry("XIC(A)MOV(Arr[Idx[1]],B)OTE(C);"),
        0,
        0,
    )
    assert c.instruction_delta() == (["MOV(Arr[Idx[1]],B)"], ["MOV(Arr[Idx[0]],B)"])


def test_plcopen_changes_ignore_layout(examples: Path) -> None:
    diffs = diff_documents(
        load(examples / "pump_station_v1.xml"), load(examples / "pump_station_v2.xml")
    )
    by = {d.title: d for d in diffs}
    ld = by["POU Alarms / Body (LD)"].changes
    # The contact moved from x=50 to x=60: not a change. Only the new coil is.
    assert [(c.op, c.new.text if c.new else "") for c in ld] == [
        ("added", 'coil negated="false": GVL.xHorn')
    ]
    st = by["POU FB_Pump / Body (ST)"].changes
    assert [c.name for c in st] == ["Line 5"]


def test_reports(examples: Path) -> None:
    diffs = diff_documents(load(examples / "conveyor_v1.L5X"), load(examples / "conveyor_v2.L5X"))
    text = text_report(diffs, "v1", "v2")
    assert "~ Rung 0   +XIO(EStop)" in text
    assert "- // Jam detection: photo eye blocked for 3 s" in text
    assert "\033[" not in text
    assert "\033[" in text_report(diffs, "v1", "v2", color=True)
    md = markdown_report(diffs, "v1", "v2")
    assert "```diff" in md
    assert "@@ Rung 4 (added) @@" in md
    data = json.loads(json_report(diffs, "v1", "v2"))
    assert data["summary"].startswith("2 rungs changed")
    assert data["blocks"][0]["changes"][0]["new"]["text"].startswith("EStop alias")
