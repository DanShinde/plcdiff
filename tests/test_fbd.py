from __future__ import annotations

from conftest import l5x

from plcdiff import loads
from plcdiff.diff import diff_documents

SHEET = """<Programs><Program Name="P"><Routines>
<Routine Name="F" Type="FBD"><FBDContent SheetSize="Letter"><Sheet Number="1">
<IRef ID="0" X="100" Y="100" Operand="Start"/>
<IRef ID="1" X="100" Y="140" Operand="Run"/>
<IRef ID="2" X="100" Y="180" Operand="Stop"/>
<Block Type="BOR" ID="3" X="200" Y="100" Operand="BOR_01" VisiblePins="In1 In2 Out"/>
<Block Type="BNOT" ID="4" X="200" Y="180" Operand="BNOT_01" VisiblePins="In Out"/>
<Block Type="BAND" ID="5" X="300" Y="100" Operand="BAND_01" VisiblePins="In1 In2 Out"/>
<ORef ID="6" X="400" Y="100" Operand="Run"/>
<IRef ID="7" X="300" Y="220" Operand="{preset}"/>
<Block Type="TONR" ID="8" X="400" Y="200" Operand="JamTimer" VisiblePins="TimerEnable PRE DN"/>
<ORef ID="9" X="500" Y="200" Operand="JamAlarm"/>
<IRef ID="10" X="100" Y="300" Operand="Level"/>
<Function Type="GRT" ID="11" X="200" Y="300" VisiblePins="SourceA SourceB"/>
<IRef ID="12" X="100" Y="340" Operand="80.0"/>
<ICon ID="14" X="300" Y="300" Name="HighLvl"/>
<OCon ID="13" X="100" Y="400" Name="HighLvl"/>
<ORef ID="15" X="200" Y="400" Operand="HighAlarm"/>
<AddOnInstruction Name="Valve" ID="16" X="300" Y="500" Operand="V1" VisiblePins="Open Opened"/>
<ORef ID="17" X="400" Y="500" Operand="V1_Open"/>
<TextBox ID="18" X="10" Y="10" Width="100">Run latch with stop</TextBox>
<Wire FromID="0" ToID="3" ToParam="In1"/>
<Wire FromID="1" ToID="3" ToParam="In2"/>
<Wire FromID="2" ToID="4" ToParam="In"/>
<Wire FromID="3" FromParam="Out" ToID="5" ToParam="In1"/>
<Wire FromID="4" FromParam="Out" ToID="5" ToParam="In2"/>
<Wire FromID="5" FromParam="Out" ToID="6"/>
<Wire FromID="5" FromParam="Out" ToID="8" ToParam="TimerEnable"/>
<Wire FromID="7" ToID="8" ToParam="PRE"/>
<Wire FromID="8" FromParam="DN" ToID="9"/>
<Wire FromID="10" ToID="11" ToParam="SourceA"/>
<Wire FromID="12" ToID="11" ToParam="SourceB"/>
<Wire FromID="11" ToID="14"/>
<Wire FromID="13" ToID="15"/>
<Wire FromID="1" ToID="16" ToParam="Open"/>
<Wire FromID="16" FromParam="Opened" ToID="17"/>
</Sheet></FBDContent></Routine></Routines></Program></Programs>"""

TITLE = "Program P / Routine F (FBD)"


def lines(preset: str = "5000") -> list[tuple[str, str]]:
    body = SHEET.format(preset=preset)
    return [(e.text, e.note) for e in loads(l5x(body)).by_title()[TITLE].entries]


def test_sheet_statements() -> None:
    assert lines() == [
        ("SHEET 1", "Run latch with stop"),
        ("Run := (Start OR Run) AND NOT Stop", ""),
        (
            "TONR JamTimer(TimerEnable := (Start OR Run) AND NOT Stop, PRE := 5000, DN => JamAlarm)",
            "",
        ),
        ("HighAlarm := Level > 80.0", ""),
        ("Valve V1(Open := Run, Opened => V1_Open)", ""),
    ]


def test_layout_is_not_a_change() -> None:
    body = SHEET.format(preset="5000")
    moved = body.replace('X="400"', 'X="420"').replace('Y="100"', 'Y="120"')
    assert diff_documents(loads(l5x(body)), loads(l5x(moved))) == []


def test_changed_operand_shows_in_statement() -> None:
    old = loads(l5x(SHEET.format(preset="5000")))
    new = loads(l5x(SHEET.format(preset="8000")))
    (d,) = diff_documents(old, new)
    (c,) = d.changes
    assert c.new is not None and "PRE := 8000" in c.new.text


def test_feedback_loop_is_cut() -> None:
    body = """<Programs><Program Name="P"><Routines>
    <Routine Name="F" Type="FBD"><FBDContent><Sheet Number="1">
    <IRef ID="0" Operand="Set"/>
    <Block Type="BOR" ID="1" Operand="BOR_01"/>
    <ORef ID="2" Operand="Latch"/>
    <Wire FromID="0" ToID="1" ToParam="In1"/>
    <Wire FromID="1" FromParam="Out" ToID="1" ToParam="In2"/>
    <Wire FromID="1" FromParam="Out" ToID="2"/>
    </Sheet></FBDContent></Routine></Routines></Program></Programs>"""
    entries = loads(l5x(body)).by_title()[TITLE].entries
    assert entries[1].text == "Latch := Set OR BOR_01.Out"
