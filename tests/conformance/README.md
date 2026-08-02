# Parser conformance fixtures

Cases for `brief_ast` / `flow_ast` per [parser-contract](../../doc/technology/parser-contract.md).

- `cases/*.py` — source fixtures (must parse with `ast.parse` unless named `*_syntax_error*`)
- `test_load_cases.py` — T004 skeleton (load only)
- Later: brief asserts (T006+), flow goldens (T005/T028)

Run: `.venv/bin/pytest tests/conformance/ -q`
