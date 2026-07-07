> **Language / Мова:** English | [Українська](../github-integration-plan.md)

# Codimension GitHub Integration Plan

**Version:** 1.3  
**Date:** 2026-07  
**Status:** Completed (Phases 1.3, 2–5); CI updated 2026-07 (mypy core, pytest 46, pip-audit mistune 3)

---

## 1. Current State

### 1.1 What Already Exists

| Component | Status | File/Location |
| --------- | ------ | ------------- |
| CI (lint) | ✅ | `.github/workflows/ci.yml` |
| Ruff check | ✅ | codimension, cdmplugins |
| Ruff format | ✅ | codimension, cdmplugins |
| Mypy | ✅ | codimension, cdmplugins (flowui/everything.py excluded) |
| Smoke test | ✅ | `import codimension; import cdmplugins`; smoke job: `pip install -r requirements.txt` |
| Pytest | ✅ | 46 tests in `tests/` |
| pip-audit | ✅ | `pip-audit -r requirements.txt` (mistune>=3.2.1) |
| README | ✅ | Badges (CI, Python, License), links |
| CONTRIBUTING | ✅ | PR template, issue templates, CI |
| Issue templates | ✅ | bug_report, feature_request, config.yml |
| PR template | ✅ | `.github/pull_request_template.md` |
| Dependabot | ✅ | `.github/dependabot.yml` |
| CI cache | ✅ | pip cache (setup-python) |
| Release workflow | ✅ | `.github/workflows/release.yml` |
| pyproject.toml | ✅ | Repository, Homepage, build-system |
| .gitignore | ✅ | venv, build, dist |

### 1.2 What Is Missing (Optional)

- Branch protection rules (configured in GitHub UI)
- CodeQL / security scanning
- GUI smoke test (xvfb)

---

## 2. Phased Implementation Plan

### Phase 1: CI Stabilization (priority: high)

| Step | Action | Input | Output | Risks |
| ---- | ------ | ----- | ------ | ----- |
| 1.1 | Fix smoke test | `codimension --help` fails without DISPLAY | Use `xvfb-run` or import check | Qt requires X11 |
| 1.2 | Add `continue-on-error` for smoke (temporary) | — | CI does not fail on smoke | Masks real errors |
| 1.3 | pip/venv caching in CI | Build time | `actions/cache` for .venv | Cache size |

**Recommendation:** 1.1 — `xvfb-run codimension --help` or `python -c "from codimension.codimension import main"` (without launching GUI).

---

### Phase 2: Issue and PR Templates (priority: medium)

| Step | Action | Files | Description |
| ---- | ------ | ----- | ----------- |
| 2.1 | Issue: Bug report | `.github/ISSUE_TEMPLATE/bug_report.md` | Fields: version, OS, Python, reproduction steps |
| 2.2 | Issue: Feature request | `.github/ISSUE_TEMPLATE/feature_request.md` | Fields: description, motivation, alternatives |
| 2.3 | Issue: Config | `.github/ISSUE_TEMPLATE/config.yml` | Issue type selection, labels |
| 2.4 | PR template | `.github/pull_request_template.md` | Checklist: ChangeLog, ruff/mypy, documentation |

---

### Phase 3: Documentation and Badges (priority: low)

| Step | Action | File | Description |
| ---- | ------ | ---- | ----------- |
| 3.1 | CI badge | README.md | `![CI](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml/badge.svg)` |
| 3.2 | Python badge | README.md | `![Python](https://img.shields.io/badge/python-3.10+-blue.svg)` |
| 3.3 | License badge | README.md | GPL v3 |
| 3.4 | Update CONTRIBUTING | CONTRIBUTING.md | Links to issue/PR templates, CI |

---

### Phase 4: Dependencies and Security (priority: medium)

| Step | Action | File | Description |
| ---- | ------ | ---- | ----------- |
| 4.1 | Dependabot | `.github/dependabot.yml` | pip and GitHub Actions updates |
| 4.2 | pip-audit in CI | ci.yml | Dependency vulnerability checks |
| 4.3 | CodeQL (optional) | `.github/workflows/codeql.yml` | Static security analysis |

---

### Phase 5: Release Workflow (priority: low)

| Step | Action | File | Description |
| ---- | ------ | ---- | ----------- |
| 5.1 | Release workflow | `.github/workflows/release.yml` | Trigger: tag v*, build, twine upload |
| 5.2 | Secrets | GitHub Secrets | `PYPI_API_TOKEN` for twine |
| 5.3 | Sync with NOTES.md | — | Automate steps 1–10 from NOTES |

---

### Phase 6: Tests (priority: as needed)

| Step | Action | Description |
| ---- | ------ | ----------- |
| 6.1 | pytest in CI | Add `pytest` job | Few tests existed at plan time |
| 6.2 | Coverage report | pytest-cov, upload to Codecov/Coveralls | Requires tests |
| 6.3 | Living Specification | doc/plugins/living-specification.md | Matrix already exists |

---

## 3. Dependencies Between Phases

```
Phase 1 (CI stabilization) — mandatory first
    ↓
Phase 2 (Issues/PR) — independent
Phase 3 (Badges) — independent
    ↓
Phase 4 (Dependabot, pip-audit) — depends on stable CI
    ↓
Phase 5 (Release) — optional after Phase 1
Phase 6 (Tests) — long-term
```

---

## 4. Environment Variables and Secrets

| Name | Purpose | Used In |
| ---- | ------- | ------- |
| `PYPI_API_TOKEN` | PyPI token (pypi-xxx) | release.yml, twine upload |
| `DISPLAY` | X11 display (for GUI) | Smoke test with xvfb |
| `QT_QPA_PLATFORM` | `offscreen` for headless Qt | xvfb alternative |

---

## 5. Limitations and Risks

| Risk | Mitigation |
| ---- | ---------- |
| codimension is a GUI app and needs a display | xvfb-run or import check instead of --help |
| PyPI token in secrets | Release only, not for PRs |
| Dependabot — many PRs | Configure grouped updates, ignore major versions |
| CodeQL — long run time | Separate workflow, does not block merge |

---

## 6. Readiness Criteria

- [x] Smoke test passes in CI without failure
- [x] Issue/PR templates created
- [x] README contains CI badge
- [x] CONTRIBUTING updated
- [x] Dependabot configured
- [x] pip-audit in CI
- [x] Release workflow ready
- [x] pip caching in CI

---

## 7. Minimum Execution Order

1. **Phase 1.1** — fix smoke test (xvfb or import check)
2. **Phase 2** — create issue/PR templates
3. **Phase 3.1** — add CI badge to README
4. **Phase 4.1** — Dependabot (if auto-updates are needed)

The rest — according to project priority.
