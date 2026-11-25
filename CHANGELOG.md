# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-25

### Added

- Siemens TIA Portal SimaticML exports: blocks (OB, FB, FC, DB), PLC data types and PLC tag
  tables. LAD/FBD networks are decoded into one statement per output, SCL is compared line by
  line, and export noise (TIA version, timestamps, `ID`/`UId` numbering) is ignored.

- Ladder rung changes show the logic: for each output instruction whose condition changed, the
  condition before and after (`OTE(Run) when (Start OR Run) AND NOT Stop`), in text, Markdown
  and JSON output (`logic` field).

- Rockwell FBD routines are decoded from their wiring into one statement per output instead
  of one line per drawn element, so moving a block on the sheet is no longer a change and a
  rewired input shows as a changed expression.

### Fixed

- Summary line pluralizes nouns ending in "y" ("2 properties changed", not "propertys").

## [0.1.0] - 2026-11-22

### Added

- Parsers for Rockwell `.L5X` and PLCopen TC6 XML exports into a stable, line-oriented view.
- `plcdiff textconv` git driver and `plcdiff install` to set it up.
- `plcdiff diff`: semantic diff with rung renumbering handled, instruction-level deltas,
  tag values, and text / Markdown / JSON output.
- `plcdiff git`: diff every PLC export changed in a revision range.
- Composite GitHub Action that writes the report to the job summary.
