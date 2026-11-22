# Contributing to plcdiff

Thanks for helping! Bug reports with a sample export are the most useful contribution of all.

## Reporting a parsing problem

Please attach the smallest export that shows the problem. Strip anything confidential first:
rename tags and routines, remove unrelated programs, delete `<Data Format="L5K">` blocks.
Tell us which software and version produced the file (e.g. Studio 5000 v35, CODESYS 3.5 SP20).

## Development

```console
git clone https://github.com/DanShinde/plcdiff
cd plcdiff
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

- Parsers live in `src/plcdiff/l5x.py` and `src/plcdiff/plcopen.py`. Each turns XML into a
  `Document` of `Block`s (see `model.py`); the diff and output code is format-agnostic.
- A new format means a new module with a `parse(root) -> Document` function and one line in
  `loader.py`.
- Add a test for every change. Fixtures that need a whole project go in `examples/`.
- Keep the package dependency-free.

## Pull requests

Small, focused PRs are easiest to review. Add a line to `CHANGELOG.md` under *Unreleased*.
