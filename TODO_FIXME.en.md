# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-03 (re-audit master@179cb0a4 + in-tree P0 hotfix)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (re-audit 2026-08-03)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| A01 | Red master CI (Ruff I001) + sequential lint gates | P0 | 🔧 hotfix: I001 + independent jobs |
| A02 | VENV silent configured→`sys.executable`; pip/recreate IDE env | P0 | 🔧 hotfix: `SOURCE_INVALID` + mutate guards |
| A03 | VENV sync `subprocess.run` blocks GUI | P0 | ✅ `ui/venvprocess.py` (QProcess + progress/cancel) |
| A04 | brief_ast: module-level defs inside control-flow | P0 | 🔧 hotfix: module `_iter_suite_statements` |
| A05 | flow_ast: `ImportFrom.level`; half-open spans; case header | P0 | ✅ half-open `_body_from_abs_range` + root `end=len` |
| A06 | Docs overstated DONE/CI-green | P0 | 🔧 this file / Living Spec |
| A07 | Comment binder: tokenize char vs AST byte columns; nested trailing | P1 | ✅ char API + nested trailing ownership |
| A08 | brief_ast: name/colon positions | P1 | 🔓 OPEN |
| A09 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN |
| A10 | `updateProperties` / `onProjectFileUpdated` without schema validate | P2 | 🔓 OPEN |
| A11 | `Settings.flush` not atomic | P2 | 🔓 OPEN |
| A12 | T130 nightly: IMPLEMENTED / NOT YET VERIFIED (0 runs) | P2 | 🔓 OPEN |
| A14 | `profgraph.Function.paint`: `drawPixmap(QRectF, pixmap)` invalid on PyQt5 | P0 | 🔧 fixed: 3-arg with sourceRect |

## Completed 2026-08 basis (T001–T141)

Remediation infrastructure is **present in code**, but that does **not** mean production-ready or that all gates are green without CI verification.

| Block | Code | Verification |
|-------|------|--------------|
| Parsers / conformance (T001–T029) | ✅ | partial; see A04–A08 |
| Tooling / credentials / scan (T030–T052) | ✅ | scan lifecycle A09 |
| Packaging / CI / core (T060–T085) | ✅ | CI layout A01 |
| Debugger e2e (T100–T130) | ✅ code | T130 nightly A12 |
| Project VENV + Env: (T140–T141) | ✅ UI | safety A02 ✅; async A03 ✅ |

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
| **Unit tests** | `pytest tests/` — **181** passed / 2 skipped (local after A03/A05) |
| **CI** | independent jobs: ruff / ruff-format / mypy / import-gates / test / wheel / smoke; `permissions: contents: read` |
| **Living Spec** | must list OPEN audit items, not only `[x] CI passes` |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
