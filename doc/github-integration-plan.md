# План інтеграції Codimension з GitHub

> **Мова / Language:** Українська | [English](en/github-integration-plan.md)

**Версія:** 1.4  
**Дата:** 2026-08-03  
**Статус:** Виконано (Фази 1–5); CI актуалізовано 2026-08 (matrix 3.10–3.13, 173 pytest, wheel, offscreen GUI, debugger_session, T072/T085)

---

## 1. Поточний стан

### 1.1 Що вже є

| Компонент | Статус | Файл/місце |
| --------- | ------ | ---------- |
| CI (lint) | ✅ | `.github/workflows/ci.yml` |
| Ruff check | ✅ | codimension, cdmplugins |
| Ruff format | ✅ | codimension, cdmplugins |
| Mypy | ✅ | codimension, cdmplugins (flowui/everything.py excluded) |
| Smoke test | ✅ | `import codimension; import cdmplugins` |
| Offscreen GUI smoke | ✅ | `scripts/offscreen_gui_smoke.py` (`QT_QPA_PLATFORM=offscreen`) |
| Pytest | ✅ | **173** tests у `tests/`; matrix Python **3.10–3.13** |
| Debugger session gate | ✅ | `pytest tests/debugger/ -m debugger_session` |
| T072 / T085 gates | ✅ | package-relative imports; core import graph |
| Wheel + pip check | ✅ | clean venv install job |
| pip-audit | ✅ | `pip-audit -r requirements.txt` |
| Nightly full-IDE smoke | ✅ | `debugger-full-ide-nightly.yml` (не PR-blocker) |
| README | ✅ | Badges (CI, Python, License), посилання |
| CONTRIBUTING | ✅ | PR template, issue templates, CI |
| Issue templates | ✅ | bug_report, feature_request, config.yml |
| PR template | ✅ | `.github/pull_request_template.md` |
| Dependabot | ✅ | `.github/dependabot.yml` |
| CI cache | ✅ | pip cache (setup-python) |
| Release workflow | ✅ | `.github/workflows/release.yml` |
| pyproject.toml | ✅ | Repository, Homepage, build-system |
| .gitignore | ✅ | venv, build, dist, `.omx`, caches |

### 1.2 Branch protection / release (G01 / E03)

- Required status check on `master`: **`ci-gate`** (aggregates ruff/format/mypy/import-gates/test/wheel/smoke/docs)
- Release workflow verifies tag↔version, constraints, pytest, `twine check`, clean wheel install + offscreen smoke, then publishes via **Trusted Publishing (OIDC)** — no long-lived `PYPI_API_TOKEN`
- Dependency snapshot: `constraints.txt` (regenerate with `python scripts/generate_constraints.py`)

---

## 2. План почергової реалізації

### Фаза 1: Стабілізація CI (пріоритет: високий)

| Крок | Дія | Вхід | Вихід | Ризики |
| ---- | --- | ---- | ----- | ------ |
| 1.1 | Виправити smoke test | `codimension --help` падає без DISPLAY | Використати `xvfb-run` або перевірку імпорту | Qt вимагає X11 |
| 1.2 | Додати `continue-on-error` для smoke (тимчасово) | — | CI не падає на smoke | Маскує реальні помилки |
| 1.3 | Кешування pip/venv у CI | Час збірки | `actions/cache` для .venv | Розмір кешу |

**Рекомендація:** 1.1 — `xvfb-run codimension --help` або `python -c "from codimension.codimension import main"` (без запуску GUI).

---

### Фаза 2: Шаблони Issues та PR (пріоритет: середній)

| Крок | Дія | Файли | Опис |
| ---- | --- | ----- | ---- |
| 2.1 | Issue: Bug report | `.github/ISSUE_TEMPLATE/bug_report.md` | Поля: версія, ОС, Python, кроки відтворення |
| 2.2 | Issue: Feature request | `.github/ISSUE_TEMPLATE/feature_request.md` | Поля: опис, мотивація, альтернативи |
| 2.3 | Issue: Config | `.github/ISSUE_TEMPLATE/config.yml` | Вибір типу issue, labels |
| 2.4 | PR template | `.github/pull_request_template.md` | Чекліст: ChangeLog, ruff/mypy, документація |

---

### Фаза 3: Документація та бейджі (пріоритет: низький)

| Крок | Дія | Файл | Опис |
| ---- | --- | ---- | ---- |
| 3.1 | Badge CI | README.md | `![CI](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml/badge.svg)` |
| 3.2 | Badge Python | README.md | `![Python](https://img.shields.io/badge/python-3.10+-blue.svg)` |
| 3.3 | Badge License | README.md | GPL v3 |
| 3.4 | Оновити CONTRIBUTING | CONTRIBUTING.md | Посилання на issue/PR templates, CI |

---

### Фаза 4: Залежності та безпека (пріоритет: середній)

| Крок | Дія | Файл | Опис |
| ---- | --- | ---- | ---- |
| 4.1 | Dependabot | `.github/dependabot.yml` | Оновлення pip, GitHub Actions |
| 4.2 | pip-audit у CI | ci.yml | Перевірка вразливостей залежностей |
| 4.3 | CodeQL (опційно) | `.github/workflows/codeql.yml` | Статичний аналіз безпеки |

---

### Фаза 5: Release workflow (пріоритет: низький)

| Крок | Дія | Файл | Опис |
| ---- | --- | ---- | ---- |
| 5.1 | Release workflow | `.github/workflows/release.yml` | Tag v*: verify (tests/twine/wheel/smoke) then OIDC publish |
| 5.2 | Trusted Publishing | PyPI + GitHub OIDC | No long-lived token |
| 5.3 | Синхронізація з NOTES.md | — | Автоматизація кроків з NOTES |

---

### Фаза 6: Тести (пріоритет: за потреби)

| Крок | Дія | Опис |
| ---- | --- | ---- |
| 6.1 | pytest у CI | Додати job `pytest` | Зараз тестів майже немає |
| 6.2 | Coverage report | pytest-cov, upload to Codecov/Coveralls | Потребує тестів |
| 6.3 | Living Specification | doc/plugins/living-specification.md | Матриця вже є |

---

## 3. Залежності між фазами

```
Фаза 1 (CI стабілізація) — обов'язкова перша
    ↓
Фаза 2 (Issues/PR) — незалежна
Фаза 3 (Badges) — незалежна
    ↓
Фаза 4 (Dependabot, pip-audit) — залежить від стабільного CI
    ↓
Фаза 5 (Release) — опційно після Фази 1
Фаза 6 (Тести) — довгострокова
```

---

## 4. Змінні середовища та секрети

| Назва | Призначення | Де використовується |
| ----- | ----------- | -------------------- |
| `PYPI` Trusted Publishing (OIDC) | Release publish via `pypa/gh-action-pypi-publish` (no long-lived token) | release.yml |
| `DISPLAY` | X11 display (для GUI) | Smoke test з xvfb |
| `QT_QPA_PLATFORM` | `offscreen` для headless Qt | Альтернатива xvfb |

---

## 5. Обмеження та ризики

| Ризик | Мітигація |
| ----- | --------- |
| codimension — GUI, потребує display | xvfb-run або перевірка імпорту замість --help |
| PyPI publish | Trusted Publishing (OIDC); optional GitHub Environment approval |
| Dependabot — багато PR | Налаштувати груповані оновлення, ignore для major |
| CodeQL — довгий прогон | Окремий workflow, не блокує merge |

---

## 6. Критерії готовності

- [x] Smoke test проходить у CI без падіння
- [x] Issue/PR templates створені
- [x] README містить badge CI
- [x] CONTRIBUTING оновлено
- [x] Dependabot налаштовано
- [x] pip-audit у CI
- [x] Release workflow готовий
- [x] Кешування pip у CI

---

## 7. Порядок виконання (мінімальний)

1. **Фаза 1.1** — виправити smoke test (xvfb або import check)
2. **Фаза 2** — створити issue/PR templates
3. **Фаза 3.1** — додати badge CI у README
4. **Фаза 4.1** — Dependabot (якщо потрібні авто-оновлення)

Решта — за пріоритетом проєкту.
