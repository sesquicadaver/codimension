> **Language / Мова:** English | [Українська](../../plugins/living-specification.md)

# Living Specification: Codimension Plugins

<!-- markdownlint-disable MD060 -->

**Version:** 1.2  
**Date:** 2026-08-03  
**Source:** [plugins-implementation-plan.md](plugins-implementation-plan.md)

Requirements-to-module-to-tests matrix. Updated with every plugin change.

---

## 1. Requirements → Module → Tests Matrix

| Requirement (plan) | Module | Files | Tests |
| ------------------ | ------ | ----- | ----- |
| **Phase 1: Coverage** | cdmplugins.coverage | coverage.cdmp, __init__.py, coveragedriver.py, coverageresultviewer.py | Smoke: Run with coverage (Ctrl+Shift+C), results tab |
| **Phase 2: Bandit** | cdmplugins.bandit | bandit.cdmp, __init__.py, banditdriver.py (LintDriverBase), banditresultviewer.py | Smoke: Run bandit (Ctrl+Shift+B); unit: tests/test_lint_drivers.py |
| **Phase 3: pip-audit** | cdmplugins.pipaudit | pipaudit.cdmp, __init__.py, pipauditdriver.py, pipauditresultviewer.py | Smoke: Audit dependencies (Ctrl+Shift+A), CVE tab |
| **Phase 4: Ruff format** | cdmplugins.ruffformat | ruffformat.cdmp, __init__.py, ruffformatdriver.py, ruffformatconfig.py | Smoke: Format (Ctrl+Shift+F), format-on-save (config) |
| **Phase 5: TODO panel** | cdmplugins.todopanel | todopanel.cdmp, __init__.py, todopaneldriver.py, todopanelviewer.py, todoscanner.py | Smoke: Scan TODO (Ctrl+Shift+O), unit: tests/test_todoscanner.py |
| **Reference: Ruff** | cdmplugins.ruff | ruff.cdmp, __init__.py, ruffdriver.py (LintDriverBase), ruffresultviewer.py | Smoke: Run ruff (Ctrl+Shift+R); unit: tests/test_lint_drivers.py |
| **Reference: Mypy** | cdmplugins.mypy | mypy.cdmp, mypydriver.py (JSONL) | Smoke: Ctrl+Shift+M; unit: tests/test_lint_drivers.py |
| **Reference: Pytest** | cdmplugins.pytest | pytest.cdmp, __init__.py, pytestdriver.py, pytestresultviewer.py | Smoke: Run pytest (Ctrl+Shift+T) |
| **Base class** | cdmplugins.lintdriverbase | lintdriverbase.py, process_env.py | systemEnvironment + non-blocking stop |
| **Git VCS / PAT** | cdmplugins.git | gitconfig.py, credentials.py, githubapi.py | gh→keyring→0600; tests/test_credentials_and_atomic.py |
| **Atomic `.cdm3`** | utils.atomic_io / project_schema | atomic_io.py, project_schema.py, project.py | atomic save; schema on load |
| **Project scan T050–T052** | utils.project_scan / project / watcher | project_scan.py, project.py, watcher.py | path-aware exclude; symlink visited; async scan; tests/test_project_scan.py |
| **Packaging / CI T060–T067** | pyproject / CI | pyproject.toml, requirements.txt, ci.yml, scripts/offscreen_gui_smoke.py | deps groups; matrix 3.10–3.13; wheel; offscreen smoke |
| **Shim identity T071–T073** | parsers / bootstrap | parsers/__init__.py, check_package_relative_imports.py | unified cdmpyparser/cdmcfparser aliases; T072 CI gate |
| **Headless core T080–T082** | core / infrastructure | core/syntax.py, core/flow.py, infrastructure/* | tests/test_core_headless.py |
| **Core import graph T085** | CI | scripts/check_core_import_graph.py | no Qt/UI imports in core/infrastructure |
| **MainWindow routing T083** | ui.mainwindow / mainwindow_debug | mainwindow.py, mainwindow_debug.py | MRO mixins; no extendInstance; DebuggerMixin |
| **Lazy GlobalData T084** | utils.globals | globals.py | create-on-first-call; tests/test_globals_lazy.py |
| **Debugger session e2e T100–T102** | debugger + utils.run / runmanager | run.py (`_debuggerClientPath`); tests/debugger/ | session-first offscreen: stop-at-first-line, continue, step/stop |
| **Debugger CI T103** | CI | `.github/workflows/ci.yml` | `QT_QPA_PLATFORM=offscreen pytest tests/debugger/ -m debugger_session` |
| **Debugger mixin routing T110–T111** | ui.mainwindow_debug + tests/debugger | host.py `create_mixin_host`; test_mixin_routing.py | switchDebugMode chrome + `_onDbgGo`→remoteContinue |
| **Debugger widget smoke T120** | debugger.bpwp / excpt | test_widgets_bpwp.py, test_widgets_exceptions.py; pytest-qt | offscreen panel add/clear/ignore; Skin bootstrap fixture |
| **Debugger full-IDE T130** | ui.mainwindow + utils.skin | `ide_bootstrap.py`, `test_full_ide_smoke.py`; `PACKAGE_SKIN_DIR` package-relative; `.github/workflows/debugger-full-ide-nightly.yml` | env `CDM_FULL_IDE_SMOKE=1`; nightly (not PR-blocker); monitor workflow |
| **Project venv bootstrap T140** | utils.venvbootstrap + ui.venvsetupdlg | venvbootstrap.py, venvsetupdlg.py, mainmenu; tests/test_venv_bootstrap.py | explicit VENV/Update; sync/upgrade/recreate; session overlay; no auto-on-open |
| **Analysis env refresh T141** | utils.venvbootstrap + project + status bar | `describeAnalysisPythonSource`, `requestAnalysisEnvironmentRefresh`, `Project.refreshAnalysisEnvironment`, `sbAnalysisEnv`; tests/test_venv_bootstrap.py | re-analyze after VENV/Update; Env: project/session/auto/IDE; unresolved opt-in multi-select |
| **Flow AST fallback** | codimension.parsers.flow_ast | flow_ast.py | unit: tests/test_flow_ast.py; conformance: tests/conformance/ (T004–T028.1); comment binder: parsers/comment_binder.py; UI coupling: test_flow_ui_coupling.py |
| **Brief AST fallback** | codimension.parsers.brief_ast | brief_ast.py | unit: tests/test_brief_ast.py; conformance: tests/conformance/ (T006–T018) |
| **Parser contract** | docs | [technology/parser-contract.md](../../technology/parser-contract.md), [uk](../../uk/technology/parser-contract.md) | Living Spec + conformance gates |
| **Source spans** | codimension.parsers.source_spans | source_spans.py (T003) | unit: tests/test_source_spans.py |
| **Binary hexdump** | codimension.utils.binfiles | binfiles.py | unit: tests/test_binfiles.py |
| **Markdown (mistune 3)** | codimension.utils.md | md.py | unit: tests/test_md.py |
| **FS smart zoom** | codimension.editor.flowuiwidget | flowuiwidget.py | unit: tests/test_flowuiwidget.py |
| **Debugger watchpoints** | codimension.debugger | wputils.py, editwatchpoint.py, server.py, wpointviewer.py | unit: tests/test_watchpoints.py |
| **Greenlet debugger** | codimension.debugger.client | threadextension_cdm_dbg.py, threadutils_cdm_dbg.py | unit: tests/test_greenlet_trace.py |
| **Occurrences search redo** | codimension.search | occurrencesprovider.py, searchresultsviewer.py | unit: tests/test_occurrencesprovider.py |

---

## 2. CI Checks

| Check | Command | Source |
| ----- | ------- | ------ |
| T072 import gate | `python scripts/check_package_relative_imports.py` | .github/workflows/ci.yml |
| T085 core graph | `python scripts/check_core_import_graph.py` | .github/workflows/ci.yml |
| Ruff lint | `ruff check codimension cdmplugins` | .github/workflows/ci.yml |
| Ruff format | `ruff format --check codimension cdmplugins` | .github/workflows/ci.yml |
| Mypy | `mypy $(find codimension cdmplugins -name '*.py' ! -path '*/flowui/everything.py')` | .github/workflows/ci.yml |
| Smoke | `import codimension; import cdmplugins` | .github/workflows/ci.yml |
| Offscreen GUI | `QT_QPA_PLATFORM=offscreen python scripts/offscreen_gui_smoke.py` | .github/workflows/ci.yml |
| Wheel | `python -m build` + clean venv `pip install` + `pip check` | .github/workflows/ci.yml |
| pip-audit | `pip-audit -r requirements.txt` | .github/workflows/ci.yml |
| Pytest | `pytest tests/` (173 tests; matrix 3.10–3.13) | .github/workflows/ci.yml |

---

## 3. Plan Compliance

- [x] All plugins in `cdmplugins/`
- [x] setup.py updated
- [x] requirements.txt updated
- [x] Documentation updated (plugins.md, living-specification.md)
- [ ] CI green on `master` — verify Actions; see [TODO_FIXME.en.md](../../../TODO_FIXME.en.md) A01–A06 (do not claim green without a run)
- [x] Documentation: [doc/README.md](../../README.md)

### Open re-audit items (2026-08-03)

| ID | Topic | Status |
|----|-------|--------|
| A02–A03 | VENV mutate safety / async pip | partial / OPEN |
| A05 | flow half-open span contract | OPEN |
| A07–A08 | comment binder / name-colon positions | OPEN |
| A09 | project scan thread lifecycle | OPEN |
| A12 | T130 nightly verified | OPEN (IMPLEMENTED, not verified) |

---

## 4. Updates

When adding or changing a plugin:

1. Add a row to the matrix (section 1).
2. Update setup.py (getPackages, package_data).
3. Update requirements.txt (if a new dependency is added).
4. Add a link to this document in the MR.
