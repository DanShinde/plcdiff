from __future__ import annotations

from pathlib import Path

import pytest
from conftest import l5x

from plcdiff import load, loads
from plcdiff.l5x import tag_values


def titles(doc):  # type: ignore[no-untyped-def]
    return [b.title for b in doc.blocks]


def test_example_structure(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X")
    assert doc.format == "L5X"
    assert doc.name == "Conveyor_Line1"
    assert doc.info["processor"] == "1769-L33ER"
    assert titles(doc) == [
        "Controller",
        "DataType Motor_UDT",
        "Modules",
        "Controller Tags",
        "Controller Tags (values)",
        "Programs",
        "Program MainProgram / Tags",
        "Program MainProgram / Tags (values)",
        "Program MainProgram / Routine MainRoutine (RLL)",
        "Program MainProgram / Routine SpeedCalc (ST)",
        "Tasks",
    ]


def test_rungs_keep_order_text_and_comment(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X")
    rll = doc.by_title()["Program MainProgram / Routine MainRoutine (RLL)"]
    assert rll.kind == "sequence"
    assert rll.unit == "Rung"
    assert len(rll.entries) == 5
    assert rll.entries[0].text == "[XIC(StartPB) ,XIC(Running) ]XIC(StopPB)OTE(Running);"
    assert rll.entries[0].note == "Start/stop seal-in for the infeed conveyor"
    assert rll.entries[1].note == ""


def test_structured_text_lines_keep_indentation(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X")
    st = doc.by_title()["Program MainProgram / Routine SpeedCalc (ST)"]
    assert [e.text for e in st.entries][1:3] == ["IF Running THEN", "    Conveyor1.Speed := 12.0;"]


def test_hidden_udt_members_skipped_and_bits_shown_as_bool(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X")
    members = [e.text for e in doc.by_title()["DataType Motor_UDT"].entries]
    assert "Run : BOOL" in members
    assert not any("ZZZZ" in m for m in members)


def test_alias_and_module(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X")
    tags = {e.key: e for e in doc.by_title()["Controller Tags"].entries}
    assert tags["PhotoEye"].text == "PhotoEye alias for Local:1:I.Data.4"
    assert tags["PhotoEye"].note == "Jam photo eye at transfer"
    modules = [e.text for e in doc.by_title()["Modules"].entries]
    assert "VFD_Conveyor1 : PowerFlex 525-EENET, rev 5.1, parent Local, address 192.168.1.21" in (
        modules
    )


def test_values_flattened(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X")
    values = {e.key: e.text for e in doc.by_title()["Controller Tags (values)"].entries}
    assert values["Conveyor1.Speed"] == "Conveyor1.Speed = 12.0"
    assert values["JamDelay.PRE"] == "JamDelay.PRE = 3000"
    assert values["StopPB"] == "StopPB = 1"


def test_no_values_option(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X", include_values=False)
    assert not any("(values)" in t for t in titles(doc))


def test_nested_arrays_structures_and_strings() -> None:
    import xml.etree.ElementTree as ET

    tag = ET.fromstring(
        """<Tag Name="Recipe" DataType="Recipe_UDT">
        <Data Format="Decorated"><Structure DataType="Recipe_UDT">
          <ArrayMember Name="Temps" DataType="REAL" Dimensions="2" Radix="Float">
            <Element Index="[0]" Value="20.5"/><Element Index="[1]" Value="30.0"/>
          </ArrayMember>
          <StructureMember Name="Name" DataType="STRING">
            <DataValueMember Name="LEN" DataType="DINT" Radix="Decimal" Value="3"/>
            <DataValueMember Name="DATA" DataType="STRING" Radix="ASCII"><![CDATA['ABC']]></DataValueMember>
          </StructureMember>
        </Structure></Data></Tag>"""
    )
    assert tag_values(tag) == [
        ("Recipe.Temps[0]", "20.5"),
        ("Recipe.Temps[1]", "30.0"),
        ("Recipe.Name.LEN", "3"),
        ("Recipe.Name.DATA", "'ABC'"),
    ]


def test_array_of_structures() -> None:
    import xml.etree.ElementTree as ET

    tag = ET.fromstring(
        """<Tag Name="Axes" DataType="Axis_UDT" Dimensions="2"><Data Format="Decorated">
        <Array DataType="Axis_UDT" Dimensions="2">
          <Element Index="[0]"><Structure DataType="Axis_UDT">
            <DataValueMember Name="Pos" DataType="REAL" Value="1.0"/></Structure></Element>
          <Element Index="[1]"><Structure DataType="Axis_UDT">
            <DataValueMember Name="Pos" DataType="REAL" Value="2.0"/></Structure></Element>
        </Array></Data></Tag>"""
    )
    assert tag_values(tag) == [("Axes[0].Pos", "1.0"), ("Axes[1].Pos", "2.0")]


def test_string_format_data() -> None:
    import xml.etree.ElementTree as ET

    tag = ET.fromstring(
        """<Tag Name="Msg" DataType="STRING"><Data Format="String" Length="5"><![CDATA['Hello']]></Data></Tag>"""
    )
    assert tag_values(tag) == [("Msg", "'Hello'")]


AOI = """
<AddOnInstructionDefinitions>
<AddOnInstructionDefinition Name="Valve" Revision="1.2" ExecutePrescan="false">
<Description><![CDATA[Two-position valve]]></Description>
<Parameters>
<Parameter Name="Open" TagType="Base" DataType="BOOL" Usage="Input" Required="true"/>
<Parameter Name="IsOpen" TagType="Base" DataType="BOOL" Usage="Output"/>
</Parameters>
<LocalTags>
<LocalTag Name="Timer" DataType="TIMER"><DefaultData Format="Decorated"><Structure DataType="TIMER">
<DataValueMember Name="PRE" DataType="DINT" Value="2000"/></Structure></DefaultData></LocalTag>
</LocalTags>
<Routines><Routine Name="Logic" Type="RLL"><RLLContent>
<Rung Number="0" Type="N"><Text><![CDATA[XIC(Open)TON(Timer,?,?);]]></Text></Rung>
</RLLContent></Routine></Routines>
</AddOnInstructionDefinition>
</AddOnInstructionDefinitions>
"""


def test_add_on_instruction() -> None:
    doc = loads(l5x(AOI))
    blocks = doc.by_title()
    params = [e.text for e in blocks["AOI Valve / Parameters"].entries]
    assert params == ["Revision 1.2", "Open : BOOL (Input) required", "IsOpen : BOOL (Output)"]
    assert blocks["AOI Valve / Parameters"].entries[0].note == "Two-position valve"
    assert [e.text for e in blocks["AOI Valve / Local Tags (values)"].entries] == [
        "Timer.PRE = 2000"
    ]
    assert blocks["AOI Valve / Routine Logic (RLL)"].entries[0].text == "XIC(Open)TON(Timer,?,?);"


def test_fbd_routine_uses_generic_lines() -> None:
    body = """<Programs><Program Name="P" MainRoutineName="F"><Routines>
    <Routine Name="F" Type="FBD"><FBDContent SheetSize="Letter"><Sheet Number="1">
    <IRef ID="0" X="100" Y="100" Operand="Level" HideDesc="false"/>
    <Block Type="ADD" ID="1" X="200" Y="100" Operand="ADD_01" VisiblePins="SourceA SourceB Dest"/>
    </Sheet></FBDContent></Routine></Routines></Program></Programs>"""
    doc = loads(l5x(body))
    lines = [e.text for e in doc.by_title()["Program P / Routine F (FBD)"].entries]
    assert lines[0] == 'FBDContent SheetSize="Letter"'
    assert any('Operand="ADD_01"' in line and line.startswith("    Block") for line in lines)


def test_protected_routine() -> None:
    body = """<Programs><Program Name="P"><Routines>
    <Routine Name="Secret" Type="RLL"><EncodedData EncodationType="SourceKey">xyz</EncodedData>
    </Routine></Routines></Program></Programs>"""
    doc = loads(l5x(body))
    assert doc.by_title()["Program P / Routine Secret (RLL)"].entries[0].text == (
        "(source protected)"
    )


def test_partial_routine_export() -> None:
    body = """<Programs><Program Use="Context" Name="P"><Routines>
    <Routine Use="Target" Name="R" Type="RLL"><RLLContent>
    <Rung Number="7" Type="N"><Text><![CDATA[NOP();]]></Text></Rung>
    </RLLContent></Routine></Routines></Program></Programs>"""
    doc = loads(l5x(body, target="Routine"))
    assert doc.info["target"] == "Routine Test"
    assert doc.by_title()["Program P / Routine R (RLL)"].entries[0].text == "NOP();"


def test_missing_controller() -> None:
    with pytest.raises(ValueError, match="Controller"):
        loads("<RSLogix5000Content/>")


def test_task_and_program_summary(examples: Path) -> None:
    doc = load(examples / "conveyor_v1.L5X")
    assert doc.by_title()["Tasks"].entries[0].text == (
        "MainTask : CONTINUOUS, priority 10, watchdog 500 ms, programs MainProgram"
    )
    assert doc.by_title()["Programs"].entries[0].text == "MainProgram main=MainRoutine"
