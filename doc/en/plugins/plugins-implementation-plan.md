> **Language / Мова:** English | [Українська](../../plugins/plugins-implementation-plan.md)

# Codimension IDE Plugins Implementation Plan

<!-- markdownlint-disable MD060 -->

**Version:** 1.1  
**Date:** 2025-03  
**Status:** Completed (readiness criteria met)

---

## 1. Goal and Context

### 1.1 Objective

Extend the Codimension plugin system with tools for:

- testing and code coverage (Coverage);
- security analysis (Bandit, pip-audit);
- code formatting (Ruff format / Black);
- quality control (TODO/FIXME panel).

### 1.2 Existing Architecture

- **Categories:** WizardInterface, VersionControlSystemInterface
- **Plugin template:** `*.cdmp` + `__init__.py` + `*driver.py` + `*resultviewer.py`
- **Location:** `cdmplugins/<name>/`
- **Registration:** `setup.py` getPackages(), package_data

### 1.3 Reference Plugins

| Plugin | Driver | Viewer | Hotkey |
| ------ | ------ | ------ | ------ |
| ruff | QProcess, JSON output | QTreeWidget | Ctrl+Shift+R |
| mypy | QProcess, JSON output | QTreeWidget | Ctrl+Shift+M |
| pytest | QProcess, text parse | QTreeWidget | Ctrl+Shift+T |

---

## 2. Implementation Phases

### Phase 0: Preparation (1–2 days) ✅

- [x] Create shared base class `LintDriverBase` (optional) for drivers
- [x] Verify CI compatibility (ruff, mypy in venv)
- [x] Update Living Specification: requirements → module → tests matrix

### Phase 1: Coverage (pytest-cov) ✅

**Priority:** High. Required for CI and Living Specification.

| Step | Description | Result |
| ---- | ----------- | ------ |
| 1.1 | Create `cdmplugins/coverage/` | coverage.cdmp, __init__.py ✅ |
| 1.2 | CoverageDriver: `pytest --cov --cov-report=json` | JSON coverage output ✅ |
| 1.3 | CoverageResultViewer: file tree + coverage % | Bottom panel tab ✅ |
| 1.4 | pytest integration: "Run with coverage" option | Button/menu (Ctrl+Shift+C) ✅ |
| 1.5 | Add to setup.py, requirements.txt | pytest-cov ✅ |

**Files:** `cdmplugins/coverage/` — coverage.cdmp, __init__.py, coveragedriver.py, coverageresultviewer.py  
**Dependencies:** pytest (already present), pytest-cov

---

### Phase 2: Bandit ✅

**Priority:** High. Security static analysis.

| Step | Description | Result |
| ---- | ----------- | ------ |
| 2.1 | Create `cdmplugins/bandit/` | bandit.cdmp, __init__.py ✅ |
| 2.2 | BanditDriver: `bandit -f json -q <file>` | JSON output ✅ |
| 2.3 | BanditResultViewer: file → severity → message | Same pattern as ruff/mypy ✅ |
| 2.4 | Hotkey Ctrl+Shift+B | Menu, toolbar, context ✅ |

**Files:** `cdmplugins/bandit/` — bandit.cdmp, __init__.py, banditdriver.py, banditresultviewer.py  
**Dependencies:** bandit

---

### Phase 3: pip-audit ✅

**Priority:** High. Dependency vulnerability checks.

| Step | Description | Result |
| ---- | ----------- | ------ |
| 3.1 | Create `cdmplugins/pipaudit/` | pipaudit.cdmp, __init__.py ✅ |
| 3.2 | PipAuditDriver: `pip_audit --format json` | JSON ✅ |
| 3.3 | PipAuditResultViewer: package → vuln → CVE | Tab ✅ |
| 3.4 | Context: Tools menu, buffer, project dir | Launch from multiple entry points ✅ |

**Note:** Runs at project/venv level, not per file.  
**Dependencies:** pip-audit

---

### Phase 4: Ruff format / Black ✅

**Priority:** Medium. Code formatting.

| Step | Description | Result |
| ---- | ----------- | ------ |
| 4.1 | Create `cdmplugins/ruffformat/` | cdmp, __init__.py ✅ |
| 4.2 | FormatDriver: `ruff format` | In-place format ✅ |
| 4.3 | Result: success/error in status bar | No separate tab ✅ |
| 4.4 | Option: format on save (config) | getConfigFunction, ruffformatconfig.py ✅ |

**Decision:** Used ruff format (ruff already present) — fewer dependencies.

---

### Phase 5: TODO/FIXME Panel ✅

**Priority:** Medium. Anti-stub check, Living Spec.

| Step | Description | Result |
| ---- | ----------- | ------ |
| 5.1 | Create `cdmplugins/todopanel/` | todopanel.cdmp, __init__.py ✅ |
| 5.2 | Project scan: grep TODO, FIXME, XXX, HACK | Regular expressions ✅ |
| 5.3 | TodoPanelViewer: file:line → text | Tree, click → goto ✅ |
| 5.4 | Refresh on save / timer | IDE signals ✅ |
| 5.5 | Filters: TODO only, FIXME only | Toolbar ✅ |

**Implementation:** No external dependencies (built-in search).

**Files:** `cdmplugins/todopanel/` — todopanel.cdmp, __init__.py, todopaneldriver.py, todopanelviewer.py, todoscanner.py

---

## 3. Execution Order

```
Phase 0 (preparation)
    ↓
Phase 1 (Coverage)  ← start here
    ↓
Phase 2 (Bandit)
    ↓
Phase 3 (pip-audit)
    ↓
Phase 4 (Ruff format)
    ↓
Phase 5 (TODO panel)
```

**Parallelization:** Phases 2 and 3 can run in parallel after Phase 1.

---

## 4. Project Virtual Environment

Optionally in Project Properties you can specify a **Python interpreter (venv)** — path to the venv directory or Python executable. Preferred path: Tools → Project utilities → **VENV…** / **Update VENV…** (T140): create/attach, pip sync|upgrade|recreate, session overlay or persist to `.cdm3`. After env changes — re-analyze plus status-bar **Env:** indicator (T141). When set, plugins (ruff, mypy, pytest, coverage, bandit, pip-audit, ruff format) use that interpreter for analysis instead of the system one.

- Empty field = IDE Python is used (sys.executable).
- Supported: venv/bin/python, venv/Scripts/python.exe, or path to Python.

---

## 5. Technical Requirements

### 5.1 Structure of Each Plugin

- Inherit `WizardInterface`
- `activate()` / `deactivate()` with proper cleanup
- `isIDEVersionCompatible(ideVersion)` — version check
- Menu: Tools → <Plugin>, buffer context, file context
- Tab in `sideBars['bottom']` (where appropriate)
- Hotkey (unique)

### 5.2 Updating setup.py

```python
# getPackages()
'cdmplugins.coverage',
'cdmplugins.bandit',
'cdmplugins.pipaudit',
'cdmplugins.ruffformat',  # or black
'cdmplugins.todopanel',

# package_data
('cdmplugins.coverage', 'cdmplugins/coverage/'),
('cdmplugins.bandit', 'cdmplugins/bandit/'),
...
```

### 5.3 Updating requirements.txt

```
pytest-cov>=4.0.0
bandit>=1.7.0
pip-audit>=2.0.0
# ruff format — ruff already present
```

### 5.4 Hotkeys (Proposal)

| Plugin | Key |
| ------ | --- |
| Coverage | Ctrl+Shift+C |
| Bandit | Ctrl+Shift+B |
| pip-audit | Ctrl+Shift+A |
| Format | Ctrl+Shift+F |
| TODO | Ctrl+Shift+O |

---

## 6. Testing

### 6.1 Per-plugin

- [x] Run plugin on a test file — IDE smoke test
- [x] Verify results tab — manual
- [x] Verify menu and hotkeys — manual
- [x] Deactivate without crash — manual
- [x] Unit tests: `tests/test_todoscanner.py` (todoscanner without Qt)

### 6.2 Integration

- All plugins active simultaneously — manual testing
- Tab switching — manual
- Launch from different contexts (file, directory, project) — manual

### 6.3 CI

- [x] `pip install -e .` in venv
- [x] Load check: `python -c "import codimension; import cdmplugins"`
- [x] ruff, mypy on codimension + cdmplugins
- [x] pytest tests/ — unit tests

---

## 6. Documentation

- [x] Update `doc/plugins/plugins.md` — list of new plugins
- [x] Add a short description for each plugin
- [x] Update ChangeLog with each release
- [x] Living Specification: requirements → module → test — [living-specification.md](living-specification.md)

---

## 7. Risks and Limitations

| Risk | Mitigation |
| ---- | ---------- |
| Hotkey conflicts | Check existing bindings |
| pip-audit without JSON | Parse text output |
| Coverage only with pytest | Document limitation |
| Bandit slow on large projects | Background run, cancellation support |

---

## 8. Readiness Criteria

- [x] All plugins in `cdmplugins/`
- [x] setup.py updated
- [x] requirements.txt updated
- [x] Documentation updated
- [x] CI passes (ruff, mypy) — `.github/workflows/ci.yml`
- [x] Smoke test: codimension starts, plugins activate

---

## 9. GitHub Integration (Related Plan)

GitHub integration plan: [doc/github-integration-plan.md](../github-integration-plan.md).

**Status (2025-03):** Phases 1.3, 2–5 completed:

- Issue/PR templates, Badges, CONTRIBUTING
- Dependabot, pip-audit in CI
- pip caching in CI
- Release workflow (tag v* → PyPI)

---

## 10. Git/GitHub Plugin

Plan: [git-github-plugin-plan.md](../../plugins/git-github-plugin-plan.md).

**Status (2026-07):** MVP implemented — `cdmplugins/git/` (status, commit, push, pull, branch, Create/View PR). Unit tests: `tests/test_gitstatusparser.py`.

---

## 11. Documentation Audit (2025-03)

- [x] living-specification.md: added pip-audit to CI checks
- [x] plugins.md: links to plugins-implementation-plan.md, git-github-plugin-plan.md
- [x] ui/qt.py: added missing Qt imports (QFont, QRectF, QSpinBox, etc.)
- [x] cdmplugins: replaced `from ..lintdriverbase` with `from cdmplugins.lintdriverbase` (yapsy)
