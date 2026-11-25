from __future__ import annotations

from pathlib import Path

import pytest

from plcdiff import load
from plcdiff.diff import diff_documents
from plcdiff.report import json_report, markdown_report, text_report
from plcdiff.rll import RungSyntaxError, logic_delta, rung_logic, split_args


@pytest.mark.parametrize(
    ("rung", "expected"),
    [
        ("OTE(x);", [("OTE(x)", "TRUE")]),
        ("XIC(a)XIO(b)OTE(c);", [("OTE(c)", "a AND NOT b")]),
        (
            "[XIC(Start) ,XIC(Run) ]XIO(Stop)OTE(Run);",
            [("OTE(Run)", "(Start OR Run) AND NOT Stop")],
        ),
        ("XIC(a)[OTE(b) ,XIO(c)OTL(d) ];", [("OTE(b)", "a"), ("OTL(d)", "a AND NOT c")]),
        ("XIC(a)GRT(Speed,10.5)TON(T1,?,?);", [("TON(T1,?,?)", "a AND Speed > 10.5")]),
        ("[XIC(a) ,XIC(b) XIC(c) ]MOV(Arr[i,j],B);", [("MOV(Arr[i,j],B)", "a OR (b AND c)")]),
        (
            "XIC(a)[XIC(b) ,XIC(c) ][XIC(d) ,XIC(e) ]OTE(x);",
            [("OTE(x)", "a AND (b OR c) AND (d OR e)")],
        ),
        ("XIC(a)[XIC(b) ,]OTE(z);", [("OTE(z)", "a")]),
        ("LIM(0,Level,100)AFI()OTE(x);", [("OTE(x)", "FALSE")]),
        ("XIC(Tank[Idx[1]].Full)OTU(Fill);", [("OTU(Fill)", "Tank[Idx[1]].Full")]),
    ],
)
def test_rung_logic(rung: str, expected: list[tuple[str, str]]) -> None:
    assert rung_logic(rung) == expected


def test_split_args_keeps_nested_operands() -> None:
    assert split_args("Arr[i,j],f(a,b), 3") == ["Arr[i,j]", "f(a,b)", "3"]


@pytest.mark.parametrize("rung", ["[XIC(a) ,XIC(b) OTE(c);", "XIC(a]OTE(c);", "XIC(a OTE(c);"])
def test_bad_rungs_raise(rung: str) -> None:
    with pytest.raises(RungSyntaxError):
        rung_logic(rung)


def test_logic_delta() -> None:
    old = "[XIC(Start) ,XIC(Run) ]XIO(Stop)OTE(Run);"
    new = "[XIC(Start) ,XIC(Run) ]XIO(Stop)XIO(Jam)OTE(Run)OTE(Lamp);"
    assert logic_delta(old, new) == [
        ("OTE(Run)", "(Start OR Run) AND NOT Stop", "(Start OR Run) AND NOT Stop AND NOT Jam"),
        ("OTE(Lamp)", None, "(Start OR Run) AND NOT Stop AND NOT Jam"),
    ]
    # an unchanged rung, or one that does not parse, gives nothing
    assert logic_delta("XIC(a)OTE(x);", "XIC(a)OTE(x);") == []
    assert logic_delta("garbage(", "XIC(a)OTE(x);") == []


def test_reports_show_logic(examples: Path) -> None:
    diffs = diff_documents(load(examples / "conveyor_v1.L5X"), load(examples / "conveyor_v2.L5X"))
    text = text_report(diffs, "a", "b")
    assert "+ OTE(Running) when (StartPB OR Running) AND StopPB AND NOT EStop" in text
    assert "# logic:" in markdown_report(diffs, "a", "b")
    assert '"output": "OTE(Running)"' in json_report(diffs, "a", "b")
    # a comment-only rung change has no logic lines
    assert "TON(JamDelay,?,?) when" not in text
