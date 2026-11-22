from __future__ import annotations

from pathlib import Path

from conftest import plcopen

from plcdiff import load, loads


def test_example(examples: Path) -> None:
    doc = load(examples / "pump_station_v1.xml")
    assert doc.format == "PLCopen XML"
    assert doc.name == "PumpStation"
    assert doc.info["product"] == "CODESYS CODESYS V3.5 SP19"
    blocks = doc.by_title()
    assert [e.text for e in blocks["DataType E_PumpState"].entries] == [
        "Idle := 0",
        "Running := 1",
        "Faulted := 2",
    ]
    iface = {e.key: e for e in blocks["POU FB_Pump / Interface"].entries}
    assert iface["START_LEVEL"].text == "VAR CONSTANT START_LEVEL : REAL := 2.5"
    assert iface["rLevel"].note == "Tank level in m"
    assert blocks["POU PLC_PRG / Interface"].entries[0].text == ("VAR fbPump1 : FB_Pump")
    assert "VAR aLevels : ARRAY[1..4] OF REAL" in [
        e.text for e in blocks["POU PLC_PRG / Interface"].entries
    ]


def test_st_body_lines(examples: Path) -> None:
    doc = load(examples / "pump_station_v1.xml")
    lines = [e.text for e in doc.by_title()["POU FB_Pump / Body (ST)"].entries]
    assert lines[0] == "IF NOT xEnable THEN"
    assert lines[1] == "    xRun := FALSE;"
    assert lines[2] == "ELSIF rLevel > START_LEVEL THEN"


def test_ld_ignores_layout(examples: Path) -> None:
    doc = load(examples / "pump_station_v1.xml")
    lines = [e.text for e in doc.by_title()["POU Alarms / Body (LD)"].entries]
    assert lines == [
        "leftPowerRail",
        'contact negated="false": GVL.xLevelHighSwitch',
        'coil negated="false": xHighLevel',
        "rightPowerRail",
    ]


def test_tasks_and_globals(examples: Path) -> None:
    doc = load(examples / "pump_station_v1.xml")
    blocks = doc.by_title()
    assert blocks["Configuration Device / Resource Application / Tasks"].entries[0].text == (
        "MainTask, interval T#20ms, priority 1, runs PLC_PRG:PLC_PRG, Alarms:Alarms"
    )
    gvl = [
        e.text for e in blocks["Configuration Device / Resource Application / Interface"].entries
    ]
    assert "VAR_GLOBAL xPump1Run AT %QX0.0 : BOOL" in gvl


TYPES = """
<dataTypes>
  <dataType name="T_Small"><baseType><subrangeSigned><range lower="0" upper="10"/>
    <baseType><INT/></baseType></subrangeSigned></baseType></dataType>
  <dataType name="T_Name"><baseType><string length="20"/></baseType>
    <initialValue><simpleValue value="'x'"/></initialValue></dataType>
  <dataType name="T_Ptr"><baseType><pointer><baseType><derived name="ST_Pump"/></baseType></pointer></baseType></dataType>
</dataTypes>
<pous>
  <pou name="FB_A" pouType="functionBlock">
    <interface>
      <inputVars retain="true"><variable name="a"><type><array><dimension lower="0" upper="1"/>
        <dimension lower="0" upper="2"/><baseType><DINT/></baseType></array></type>
        <initialValue><arrayValue><value repetitionValue="6"><simpleValue value="0"/></value></arrayValue></initialValue>
      </variable></inputVars>
      <localVars><variable name="s"><type><derived name="ST_X"/></type>
        <initialValue><structValue><value member="a"><simpleValue value="1"/></value></structValue></initialValue>
      </variable></localVars>
    </interface>
    <body><FBD>
      <block localId="1" typeName="ADD" instanceName="" executionOrderId="0" width="10" height="10">
        <position x="1" y="1"/>
        <inputVariables><variable formalParameter="IN1"><connectionPointIn/></variable>
          <variable formalParameter="IN2"><connectionPointIn/></variable></inputVariables>
        <inOutVariables/>
        <outputVariables><variable formalParameter="OUT"><connectionPointOut/></variable></outputVariables>
      </block>
      <inVariable localId="2"><position x="0" y="0"/><expression>a[0,0]</expression></inVariable>
      <comment localId="3" height="1" width="1"><position x="0" y="0"/><content><xhtml xmlns="http://www.w3.org/1999/xhtml">adds things</xhtml></content></comment>
    </FBD></body>
    <actions><action name="Reset"><body><ST><xhtml xmlns="http://www.w3.org/1999/xhtml">a[0,0] := 0;</xhtml></ST></body></action></actions>
    <addData><data name="http://www.3s-software.com/plcopenxml/method" handleUnknown="implementation">
      <method name="Init"><interface><inputVars><variable name="n"><type><INT/></type></variable></inputVars></interface>
      <body><ST><xhtml xmlns="http://www.w3.org/1999/xhtml">s.a := n;</xhtml></ST></body></method>
    </data></addData>
  </pou>
  <pou name="F_Sq" pouType="function">
    <interface><returnType><LREAL/></returnType></interface>
    <body><IL><xhtml xmlns="http://www.w3.org/1999/xhtml">LD 1</xhtml></IL></body>
  </pou>
</pous>
"""

GVL = """<addData><data name="http://www.3s-software.com/plcopenxml/globalvars" handleUnknown="implementation">
<globalVars name="GVL_Io" constant="true"><variable name="MAX"><type><INT/></type>
<initialValue><simpleValue value="99"/></initialValue></variable></globalVars>
</data></addData>"""


def test_types_values_methods_actions_and_codesys_gvl() -> None:
    doc = loads(plcopen(types=TYPES, add_data=GVL))
    blocks = doc.by_title()
    assert blocks["DataType T_Small"].entries[0].text == "T_Small : INT(0..10)"
    assert blocks["DataType T_Name"].entries[0].text == "T_Name : STRING(20) := 'x'"
    assert blocks["DataType T_Ptr"].entries[0].text == "T_Ptr : POINTER TO ST_Pump"
    iface = {e.key: e.text for e in blocks["POU FB_A / Interface"].entries}
    assert iface["a"] == "VAR_INPUT RETAIN a : ARRAY[0..1,0..2] OF DINT := [6(0)]"
    assert iface["s"] == "VAR s : ST_X := (a := 1)"
    fbd = [e.text for e in blocks["POU FB_A / Body (FBD)"].entries]
    assert fbd == [
        'block instanceName="" typeName="ADD" input(IN1, IN2) output(OUT)',
        "inVariable: a[0,0]",
        "comment: adds things",
    ]
    assert blocks["POU FB_A / Action Reset (ST)"].entries[0].text == "a[0,0] := 0;"
    assert blocks["POU FB_A / Method Init / Interface"].entries[0].text == "VAR_INPUT n : INT"
    assert blocks["POU FB_A / Method Init / Body (ST)"].entries[0].text == "s.a := n;"
    assert blocks["POU F_Sq / Interface"].entries[0].text == "RETURN : LREAL"
    assert blocks["POU F_Sq / Body (IL)"].entries[0].text == "LD 1"
    assert blocks["GVL GVL_Io"].entries[0].text == "VAR_GLOBAL CONSTANT MAX : INT := 99"


def test_sfc_steps_and_transitions() -> None:
    types = """<pous><pou name="Seq" pouType="program"><body><SFC>
      <step localId="1" name="Init" initialStep="true"><position x="0" y="0"/></step>
      <transition localId="2"><position x="0" y="0"/><condition><inline name="t"><ST>
        <xhtml xmlns="http://www.w3.org/1999/xhtml">xStart</xhtml></ST></inline></condition></transition>
      <actionBlock localId="3"><position x="0" y="0"/><action localId="0" qualifier="N">
        <reference name="Fill"/></action></actionBlock>
    </SFC></body></pou></pous>"""
    lines = [e.text for e in loads(plcopen(types=types)).by_title()["POU Seq / Body (SFC)"].entries]
    assert lines == [
        'step initialStep="true" name="Init"',
        "transition: xStart",
        "actionBlock: N Fill",
    ]
