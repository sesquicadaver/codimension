# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-03  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Completed audit 2026-08 (T001–T141)

All linear remediation items and VENV/env follow-ups are **DONE**. Details: [ChangeLog](ChangeLog), matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).

| Block | Status |
|-------|--------|
| Parsers / conformance (T001–T029) | ✅ DONE (T029 SKIPPED — no C-ext) |
| Tooling / credentials / project scan (T030–T052) | ✅ DONE |
| Packaging / CI / bootstrap / core (T060–T085) | ✅ DONE |
| Debugger GUI e2e (T100–T130) | ✅ DONE (T130 — nightly, not a PR blocker) |
| Project VENV + analysis env (T140–T141) | ✅ DONE |

## `pass` stubs (need review)

- **flowui/everything.py** — flow UI demo file, ignored by ruff
- **runmanager.py, mainstatusbar.py** — `pass` in except/empty handlers
- **variablesbrowser.py, notused.py, brief_ast.py** — `pass` in handlers
- **vcsannotateviewer.py, classesviewer.py** — `pass` in methods
- **profgraph.py, importsdgm.py, asyncfile_cdm_dbg.py** — `pass` in handlers
- **wpointviewer.py, editorsmanager.py** — `pass` in handlers
- **resultprovideriface.py** — abstract interface
- **profiletest.py** — profiling test file

## Infrastructure (fact)

| Topic | State |
|-------|-------|
| **Unit tests** | `pytest tests/` — **173** tests (CI matrix 3.10–3.13) |
| **mypy / ruff** | `codimension` + `cdmplugins` in CI; tools in `requirements.txt` |
| **CI** | lint + pytest; wheel+`pip check`; offscreen GUI smoke; pip-audit; T072/T085 gates; debugger_session step |
| **Lazy load Classes/Functions/Globals** | `populateIfNeeded` ✅ |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
