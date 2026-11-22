# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-22

### Added

- Parsers for Rockwell `.L5X` and PLCopen TC6 XML exports into a stable, line-oriented view.
- `plcdiff textconv` git driver and `plcdiff install` to set it up.
- `plcdiff diff`: semantic diff with rung renumbering handled, instruction-level deltas,
  tag values, and text / Markdown / JSON output.
- `plcdiff git`: diff every PLC export changed in a revision range.
- Composite GitHub Action that writes the report to the job summary.
