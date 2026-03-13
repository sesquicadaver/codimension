# План інтеграції Codimension з GitHub

**Версія:** 1.0  
**Дата:** 2025-03  
**Статус:** План

---

## 1. Поточний стан

### 1.1 Що вже є

| Компонент | Статус | Файл/місце |
| --------- | ------ | ---------- |
| CI (lint) | ✅ | `.github/workflows/ci.yml` |
| Ruff check | ✅ | codimension, cdmplugins |
| Ruff format | ✅ | codimension, cdmplugins |
| Mypy | ✅ | cdmplugins |
| Smoke test | ⚠️ | `codimension --help` (може падати без display) |
| README | ✅ | Посилання на GitHub |
| CONTRIBUTING | ✅ | Інструкції для PR |
| pyproject.toml | ✅ | Repository, Homepage URLs |
| .gitignore | ✅ | venv, build, dist |

### 1.2 Що відсутнє

- Issue templates
- PR template
- Branch protection rules (налаштовуються в GitHub UI)
- Dependabot / Renovate
- CodeQL / security scanning
- Release workflow (автоматизація PyPI)
- Badge у README
- Smoke test для GUI (xvfb)
- Unit/integration тести в CI

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
| 5.1 | Release workflow | `.github/workflows/release.yml` | Trigger: tag v*, build, twine upload |
| 5.2 | Секрети | GitHub Secrets | `PYPI_API_TOKEN` для twine |
| 5.3 | Синхронізація з NOTES.md | — | Автоматизація кроків 1–10 з NOTES |

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
| `PYPI_API_TOKEN` | Токен PyPI (pypi-xxx) | release.yml, twine upload |
| `DISPLAY` | X11 display (для GUI) | Smoke test з xvfb |
| `QT_QPA_PLATFORM` | `offscreen` для headless Qt | Альтернатива xvfb |

---

## 5. Обмеження та ризики

| Ризик | Мітигація |
| ----- | --------- |
| codimension — GUI, потребує display | xvfb-run або перевірка імпорту замість --help |
| PyPI token у секретах | Тільки для release, не для PR |
| Dependabot — багато PR | Налаштувати груповані оновлення, ignore для major |
| CodeQL — довгий прогон | Окремий workflow, не блокує merge |

---

## 6. Критерії готовності

- [ ] Smoke test проходить у CI без падіння
- [ ] Issue/PR templates створені
- [ ] README містить badge CI
- [ ] CONTRIBUTING оновлено
- [ ] Dependabot налаштовано (опційно)
- [ ] Release workflow готовий (опційно)

---

## 7. Порядок виконання (мінімальний)

1. **Фаза 1.1** — виправити smoke test (xvfb або import check)
2. **Фаза 2** — створити issue/PR templates
3. **Фаза 3.1** — додати badge CI у README
4. **Фаза 4.1** — Dependabot (якщо потрібні авто-оновлення)

Решта — за пріоритетом проєкту.
