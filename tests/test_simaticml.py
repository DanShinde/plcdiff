from __future__ import annotations

from pathlib import Path

from plcdiff import load, loads
from plcdiff.diff import diff_documents, summarize


def doc(obj: str, version: str = "V19") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        f'<Document><Engineering version="{version}" />{obj}</Document>\n'
    )


def scl_fc(tokens: str, number: int = 1) -> str:
    return doc(
        '<SW.Blocks.FC ID="0"><AttributeList>'
        '<Interface><Sections xmlns="http://www.siemens.com/automation/Openness/SW/Interface/v5">'
        '<Section Name="Input"><Member Name="a" Datatype="Int" /></Section>'
        '<Section Name="Return"><Member Name="Ret_Val" Datatype="Int" /></Section>'
        "</Sections></Interface>"
        f"<Name>FC_Calc</Name><Number>{number}</Number>"
        "<ProgrammingLanguage>SCL</ProgrammingLanguage></AttributeList>"
        '<ObjectList><SW.Blocks.CompileUnit ID="3" CompositionName="CompileUnits"><AttributeList>'
        '<NetworkSource><StructuredText xmlns="http://www.siemens.com/automation/Openness/SW/'
        f'NetworkSource/StructuredText/v3">{tokens}</StructuredText></NetworkSource>'
        "<ProgrammingLanguage>SCL</ProgrammingLanguage></AttributeList></SW.Blocks.CompileUnit>"
        "</ObjectList></SW.Blocks.FC>"
    )


def local(name: str, uid: int) -> str:
    return (
        f'<Access Scope="LocalVariable" UId="{uid}"><Symbol>'
        f'<Component Name="{name}" UId="{uid + 1}" /></Symbol></Access>'
    )


SCL = (
    '<Token Text="IF" UId="21" /><Blank UId="22" />'
    + local("a", 23)
    + '<Blank UId="25" /><Token Text="&gt;" UId="26" /><Blank UId="27" />'
    '<Access Scope="LiteralConstant" UId="28"><Constant><ConstantValue>10</ConstantValue>'
    '</Constant></Access><Blank UId="29" /><Token Text="THEN" UId="30" />'
    '<NewLine UId="31" /><Blank Num="4" UId="32" />'
    + local("Ret_Val", 33)
    + '<Blank UId="35" /><Token Text=":=" UId="36" /><Blank UId="37" />'
    + local("a", 38)
    + '<Token Text=";" UId="40" /><Blank UId="41" />'
    '<LineComment UId="42"><Text UId="43">clamp</Text></LineComment>'
    '<NewLine UId="44" /><Token Text="END_IF" UId="45" /><Token Text=";" UId="46" />'
)


def test_ladder_example(examples: Path) -> None:
    d = load(examples / "FB_Conveyor_v1.xml")
    assert d.format == "SimaticML"
    assert d.name == "FB_Conveyor"
    assert d.info["software"] == "TIA Portal V19"
    blocks = d.by_title()
    networks = [e.text for e in blocks["FB FB_Conveyor / Networks"].entries]
    assert networks == [
        "NETWORK (LAD)",
        "#Run := (#Start OR #Run) AND NOT #Stop",
        "NETWORK (LAD)",
        "TON<Time> #JamTimer(IN := #Run, PT := T#2S, Q => #JamAlarm)",
    ]
    assert blocks["FB FB_Conveyor / Networks"].entries[0].note == "Run latch"
    iface = {e.key: e for e in blocks["FB FB_Conveyor / Interface"].entries}
    assert iface["Input.Start"].text == "Input Start : Bool"
    assert iface["Input.Start"].note == "Start push button"
    values = [e.text for e in blocks["FB FB_Conveyor / Interface (values)"].entries]
    assert values == ["Speed := 1.2"]


def test_ladder_example_diff(examples: Path) -> None:
    old = load(examples / "FB_Conveyor_v1.xml")
    new = load(examples / "FB_Conveyor_v2.xml")
    diffs = {d.title: d for d in diff_documents(old, new)}
    net = diffs["FB FB_Conveyor / Networks"].changes
    assert [c.op for c in net] == ["changed", "changed", "changed"]
    assert net[0].new is not None and net[0].new.text.endswith("AND NOT #Jam")
    # comment-only change: same text, different note
    assert net[1].old is not None and net[1].new is not None
    assert net[1].old.text == net[1].new.text
    # export noise (TIA version, export time, IDs, AutoNumber) is not a change
    assert "Document" not in " ".join(diffs)
    assert "2 properties changed" in summarize(list(diffs.values()))


def test_scl_lines_and_comments() -> None:
    d = loads(scl_fc(SCL))
    lines = d.by_title()["FC FC_Calc / Networks"].entries
    assert [(e.text, e.note) for e in lines] == [
        ("NETWORK (SCL)", ""),
        ("IF #a > 10 THEN", ""),
        ("    #Ret_Val := #a;", "clamp"),
        ("END_IF;", ""),
    ]


def test_uid_and_export_noise_ignored() -> None:
    renumbered = SCL.replace('UId="2', 'UId="9')
    a = loads(scl_fc(SCL))
    b = loads(scl_fc(renumbered).replace("V19", "V20"))
    assert diff_documents(a, b) == []


def test_block_number_is_a_change() -> None:
    a = loads(scl_fc(SCL, number=1))
    b = loads(scl_fc(SCL, number=2))
    (d,) = diff_documents(a, b)
    assert d.title == "FC FC_Calc / Attributes"


def test_tag_table() -> None:
    def tag(name: str, dtype: str, address: str, comment: str = "") -> str:
        com = (
            '<ObjectList><MultilingualText CompositionName="Comment"><ObjectList>'
            "<MultilingualTextItem><AttributeList><Culture>en-US</Culture>"
            f"<Text>{comment}</Text></AttributeList></MultilingualTextItem></ObjectList>"
            "</MultilingualText></ObjectList>"
            if comment
            else ""
        )
        return (
            f'<SW.Tags.PlcTag ID="1" CompositionName="Tags"><AttributeList>'
            f"<DataTypeName>{dtype}</DataTypeName><LogicalAddress>{address}</LogicalAddress>"
            f"<Name>{name}</Name></AttributeList>{com}</SW.Tags.PlcTag>"
        )

    xml = doc(
        '<SW.Tags.PlcTagTable ID="0"><AttributeList><Name>IO</Name></AttributeList><ObjectList>'
        + tag("StartPB", "Bool", "%I0.0", "Start button")
        + tag("MotorOn", "Bool", "%Q0.0")
        + '<SW.Tags.PlcUserConstant ID="5" CompositionName="UserConstants"><AttributeList>'
        "<DataTypeName>Int</DataTypeName><Name>MAX_ZONES</Name><Value>12</Value>"
        "</AttributeList></SW.Tags.PlcUserConstant>"
        "</ObjectList></SW.Tags.PlcTagTable>"
    )
    blocks = loads(xml).by_title()
    tags = {e.key: e for e in blocks["Tag table IO"].entries}
    assert tags["StartPB"].text == "StartPB : Bool AT %I0.0"
    assert tags["StartPB"].note == "Start button"
    assert [e.text for e in blocks["Tag table IO / User constants"].entries] == [
        "MAX_ZONES : Int := 12"
    ]


def test_udt_nested_members() -> None:
    xml = doc(
        '<SW.Types.PlcStruct ID="0"><AttributeList><Interface>'
        '<Sections xmlns="http://www.siemens.com/automation/Openness/SW/Interface/v5">'
        '<Section Name="None"><Member Name="Motor" Datatype="Struct">'
        '<Member Name="Speed" Datatype="Real"><StartValue>0.5</StartValue></Member>'
        "</Member></Section></Sections></Interface><Name>typeZone</Name></AttributeList>"
        "</SW.Types.PlcStruct>"
    )
    blocks = loads(xml).by_title()
    members = [e.key for e in blocks["UDT typeZone / Interface"].entries]
    assert members == ["None.Motor", "None.Motor.Speed"]
    assert [e.text for e in blocks["UDT typeZone / Interface (values)"].entries] == [
        "Motor.Speed := 0.5"
    ]


def test_call_with_parameters() -> None:
    net = (
        '<FlgNet xmlns="http://www.siemens.com/automation/Openness/SW/NetworkSource/FlgNet/v5">'
        "<Parts>"
        '<Access Scope="GlobalVariable" UId="21"><Symbol><Component Name="IO" />'
        '<Component Name="Start" /></Symbol></Access>'
        '<Access Scope="GlobalVariable" UId="22"><Symbol><Component Name="Zone" />'
        '<Component Name="Running" /></Symbol></Access>'
        '<Call UId="23"><CallInfo Name="ZoneStart" BlockType="FB">'
        '<Instance Scope="GlobalVariable" UId="24"><Component Name="Zone1_DB" /></Instance>'
        '<Parameter Name="inStart" Section="Input" Type="Bool" />'
        '<Parameter Name="outRun" Section="Output" Type="Bool" /></CallInfo></Call>'
        "</Parts><Wires>"
        '<Wire UId="25"><Powerrail /><NameCon UId="23" Name="en" /></Wire>'
        '<Wire UId="26"><IdentCon UId="21" /><NameCon UId="23" Name="inStart" /></Wire>'
        '<Wire UId="27"><NameCon UId="23" Name="outRun" /><IdentCon UId="22" /></Wire>'
        "</Wires></FlgNet>"
    )
    xml = doc(
        '<SW.Blocks.FC ID="0"><AttributeList><Name>FC_Zones</Name>'
        "<ProgrammingLanguage>LAD</ProgrammingLanguage></AttributeList><ObjectList>"
        '<SW.Blocks.CompileUnit ID="3"><AttributeList><NetworkSource>'
        f"{net}</NetworkSource><ProgrammingLanguage>LAD</ProgrammingLanguage></AttributeList>"
        "</SW.Blocks.CompileUnit></ObjectList></SW.Blocks.FC>"
    )
    lines = [e.text for e in loads(xml).by_title()["FC FC_Zones / Networks"].entries]
    assert lines[1] == '"ZoneStart" "Zone1_DB"(inStart := "IO".Start, outRun => "Zone".Running)'
