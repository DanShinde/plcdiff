from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from plcdiff.cli import main


def test_textconv(examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["textconv", str(examples / "conveyor_v1.L5X")]) == 0
    out = capsys.readouterr().out
    assert out.startswith("# L5X: Conveyor_Line1\n")
    assert "== Program MainProgram / Routine MainRoutine (RLL) ==" in out


def test_textconv_passes_unknown_files_through(
    tmp_path: Path, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    f = tmp_path / "notes.xml"
    f.write_bytes(b"<notes>hello</notes>")
    assert main(["textconv", str(f)]) == 0
    assert capsysbinary.readouterr().out == b"<notes>hello</notes>"


def test_diff_formats_and_exit_code(examples: Path, capsys: pytest.CaptureFixture[str]) -> None:
    a, b = str(examples / "conveyor_v1.L5X"), str(examples / "conveyor_v2.L5X")
    assert main(["diff", a, b]) == 0
    assert "Rung 4" in capsys.readouterr().out
    assert main(["diff", a, b, "--exit-code", "-f", "json"]) == 1
    assert json.loads(capsys.readouterr().out)["blocks"]
    assert main(["diff", a, a, "--exit-code"]) == 0
    assert "no changes" in capsys.readouterr().out


def test_diff_bad_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "x.l5x"
    f.write_text("not xml")
    assert main(["diff", str(f), str(f)]) == 2
    assert "not well-formed" in capsys.readouterr().err


def test_module_entry_point(examples: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "plcdiff", "--version"], capture_output=True, text=True, check=True
    )
    assert proc.stdout.startswith("plcdiff ")


@pytest.fixture
def repo(tmp_path: Path, examples: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))  # keep --global writes in the sandbox
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    def git(*args: str) -> None:
        subprocess.run(["git", *args], check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "plc").mkdir()
    shutil.copy(examples / "conveyor_v1.L5X", tmp_path / "plc" / "Line1.L5X")
    shutil.copy(examples / "pump_station_v1.xml", tmp_path / "plc" / "pumps.xml")
    (tmp_path / "plc" / "other.xml").write_text("<x/>")
    git("add", ".")
    git("commit", "-q", "-m", "v1")
    shutil.copy(examples / "conveyor_v2.L5X", tmp_path / "plc" / "Line1.L5X")
    shutil.copy(examples / "pump_station_v2.xml", tmp_path / "plc" / "pumps.xml")
    (tmp_path / "plc" / "other.xml").write_text("<y/>")
    return tmp_path


def test_install_and_git_diff_uses_textconv(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exe = f'"{sys.executable}" -m plcdiff textconv'
    from plcdiff.gitutil import install

    lines = install(patterns=("*.L5X", "plc/pumps.xml"), command=exe)
    assert "plc/pumps.xml diff=plcdiff" in (repo / ".gitattributes").read_text()
    assert lines[0].startswith("git config diff.plcdiff.textconv")
    # idempotent
    install(patterns=("*.L5X",), command=exe)
    assert (repo / ".gitattributes").read_text().count("*.L5X diff=plcdiff") == 1
    out = subprocess.run(
        ["git", "diff", "--", "plc/Line1.L5X"], capture_output=True, text=True, check=True
    ).stdout
    assert "+[XIC(StartPB) ,XIC(Running) ]XIC(StopPB)XIO(EStop)OTE(Running);" in out
    assert "ExportDate" not in out


def test_install_command(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["install", "--global"]) == 0
    assert "Done." in capsys.readouterr().out
    assert (repo / ".config" / "git" / "attributes").read_text() == (
        "*.L5X diff=plcdiff\n*.l5x diff=plcdiff\n"
    )


def test_git_command_working_tree(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["git", "--exit-code", "-f", "markdown"]) == 1
    out = capsys.readouterr().out
    assert "a/plc/Line1.L5X" in out
    assert "a/plc/pumps.xml" in out
    assert "other.xml" not in out


def test_git_command_range(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    subprocess.run(["git", "commit", "-qam", "v2"], check=True)
    subprocess.run(["git", "mv", "plc/pumps.xml", "plc/pump_station.xml"], check=True)
    subprocess.run(["git", "commit", "-qm", "rename"], check=True)
    assert main(["git", "HEAD~2..HEAD", "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [d["new"] for d in data] == ["b/plc/Line1.L5X", "b/plc/pump_station.xml"]
    assert data[1]["old"] == "a/plc/pumps.xml"
    assert main(["git", "HEAD~1..HEAD"]) == 0
    assert capsys.readouterr().out == "No PLC program changes.\n"


def test_git_outside_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert main(["git"]) == 2
