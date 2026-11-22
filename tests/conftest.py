from __future__ import annotations

from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def examples() -> Path:
    return EXAMPLES


def l5x(body: str, target: str = "Controller") -> str:
    """Wrap controller content in a minimal L5X envelope."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="35.00" '
        f'TargetName="Test" TargetType="{target}">\n'
        f'<Controller Use="Target" Name="Test" ProcessorType="1756-L85E">{body}</Controller>\n'
        "</RSLogix5000Content>\n"
    )


def plcopen(types: str = "", instances: str = "", add_data: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<project xmlns="http://www.plcopen.org/xml/tc6_0201">'
        '<fileHeader companyName="ACME" productName="CODESYS" productVersion="3.5"/>'
        '<contentHeader name="Proj"/>'
        f"<types>{types}</types>"
        f"<instances><configurations>{instances}</configurations></instances>"
        f"{add_data}"
        "</project>\n"
    )
