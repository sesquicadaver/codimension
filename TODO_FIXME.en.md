# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-02  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension  
**Linear plan:** [.omx/plans/linear-remediation-atomic-20260802.md](.omx/plans/linear-remediation-atomic-20260802.md)

## Critical (core correctness) — audit 2026-08-02

| Plan ID | Area | Description | Status |
|---------|------|-------------|--------|
| T010–T018 | `brief_ast.py` | Missing `async def`; inverted instance attrs; defaults overwrite last arg; incomplete 3.10+ grammar | 🔴 TODO |
| T020–T028 | `flow_ast.py` | UTF-8 byte spans mishandled; O(n²) `_abs_pos`; empty comments/CML; match/except*/docstrings | 🔴 TODO |
| T034–T035 | `mypydriver.py` | Expects `{"files":...}`; mypy emits JSONL | 🔴 TODO |
| T030–T033 | lint/tool drivers | Empty `QProcessEnvironment()`; blocking kill/wait | 🔴 TODO |
| T040–T041 | `gitconfig.py` | Plaintext GitHub PAT | 🔴 TODO |
| T042–T051 | `project.py` | Non-atomic `.cdm3`; basename exclusions; symlink cycles | 🔴 TODO |
| T060–T067 | packaging/CI | Missing `[project.dependencies]`; CI ≠ claimed 3.10–3.13 matrix | 🔴 TODO |

## Critical (anti-stub review) — earlier

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
| **Unit tests** | 46 tests. Parser conformance / CFG snapshots → plan T004–T028. |
| **mypy** | Packages in CI | ✅ 2026-07-05 (output parser → T034) |
| **CI truth** | Lint 3.10–3.12; pytest only 3.11; no 3.13 / wheel / offscreen GUI → T063–T066 |

See [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
