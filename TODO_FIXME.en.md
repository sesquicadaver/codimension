# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-02  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension  
**Linear plan:** [.omx/plans/linear-remediation-atomic-20260802.md](.omx/plans/linear-remediation-atomic-20260802.md)

## Critical (core correctness) — audit 2026-08-02

| Plan ID | Area | Description | Status |
|---------|------|-------------|--------|
| T010–T018 | `brief_ast.py` | brief M1 foundation | ✅ DONE 2026-08-02 |
| T020–T028.C | `flow_ast` + `comment_binder` | M2 Flow Foundation | ✅ DONE 2026-08-02 |
| T029 | differential report | C-ext absent → explicit skip | ✅ SKIPPED (documented) |
| T030–T035 | process_env + lint/mypy | systemEnvironment; JSONL; non-blocking stop | ✅ DONE 2026-08-02 |
| T040–T044 | credentials + atomic_io + schema | gh→keyring→0600; scrub; atomic `.cdm3` | ✅ DONE 2026-08-02 |
| T050–T052 | `project_scan` / `project` / `watcher` | Path-aware exclude; symlink bounds; async scan | ✅ DONE 2026-08-02 |
| T060–T067 | packaging/CI | deps groups; matrix 3.10–3.13; wheel; offscreen | ✅ DONE 2026-08-02 |
| T070 | `codimension.py` | `originalSysPath = list(sys.path)` | ✅ DONE 2026-08-02 |
| T071–T073 | bootstrap / imports | inventory + T072 CI gate + shim `_unify_aliases` | ✅ DONE 2026-08-02 |
| T080–T082 | `core` / `infrastructure` | headless syntax/flow + fs/io/process facades | ✅ DONE 2026-08-02 |
| T085 | `scripts/check_core_import_graph.py` | CI: no Qt/UI edges into core | ✅ DONE 2026-08-02 |
| T083–T084 | MainWindow / GlobalData | composition routing; remove extendInstance side effects | 🟠 TODO (after T080–T082) |

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
| **CI truth** | Lint+pytest 3.10–3.13; wheel+pip check; offscreen GUI smoke (T063–T066 done) |

See [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
