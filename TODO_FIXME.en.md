# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-07-06  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Critical (anti-stub review)

| File | Line | Description | Status |
|------|------|-------------|--------|
| `codimension/utils/binfiles.py` | — | hexdump via subprocess | ✅ Fixed 2026-07-04 |
| `codimension/editor/flowuiwidget.py` | — | FS smart zoom enabled (SMART_ZOOM_MAX) | ✅ Fixed 2026-07-04 |
| `codimension/utils/md.py` | — | mistune 3.x migration | ✅ Fixed 2026-07-04 |
| `codimension/search/occurrencesprovider.py` | — | searchAgain stub (`pass`) | ✅ Fixed 2026-07-05 |

## Fixed (2026-07-04)

| File | Description |
|------|-------------|
| `codimension/parsers/flow_ast.py` | `from X import` — `_pos(node.module)` replaced with span from source |
| `codimension/ui/editorsmanager.py` | `onHighlightInFS` — inverted condition |
| `codimension/diagram/depsitems.py` | Connector on scene for deps diagram |

## Explicit TODO markers

| File | Line | Description |
|------|------|-------------|
| `codimension/debugger/bpwp.py` | — | WatchPointViewer enabled in debugger panel | ✅ Fixed 2026-07-05 |
| `codimension/debugger/server.py` | — | `__sendWatchpoints` sync to debuggee | ✅ Fixed 2026-07-05 |
| `codimension/debugger/client/threadextension_cdm_dbg.py` | — | greenlet.settrace debugger extension | ✅ Fixed 2026-07-05 |

## `pass` stubs (need review)

- **flowui/everything.py** — flow UI demo file, ignored by ruff
- **runmanager.py, mainstatusbar.py** — `pass` in except/empty handlers
- **variablesbrowser.py, notused.py, brief_ast.py** — `pass` in handlers
- **vcsannotateviewer.py, classesviewer.py** — `pass` in methods
- **profgraph.py, importsdgm.py, asyncfile_cdm_dbg.py** — `pass` in handlers
- **wpointviewer.py, editorsmanager.py** — `pass` in handlers
- **resultprovideriface.py** — abstract interface
- **profiletest.py** — profiling test file

## Infrastructure

| Issue | Status |
|-------|--------|
| **Unit tests** | 46 tests in `tests/` (pytest). Extend CFG snapshot coverage. |
| **mypy** | `codimension` + `cdmplugins` in CI | ✅ 2026-07-05 |
| **ruff/mypy in venv** | In `requirements.txt` | ✅ |
| **README / INSTALL** | Source-only install, Python 3.10+ | ✅ 2026-07-06 |
| **excludeFromAnalysis, venv exclusion** | doc/uk/project/project.md | ✅ |
| **Lazy load Classes/Functions/Globals** | populateIfNeeded | ✅ |

## CI recommendations

All items are in `.github/workflows/ci.yml`:

1. `ruff check` / `ruff format --check`
2. `mypy` on codimension + cdmplugins
3. `pytest tests/`
4. `pip-audit -r requirements.txt`
5. Smoke: `import codimension; import cdmplugins`

See [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
