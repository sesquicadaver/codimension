# Living Specification: Плагіни Codimension

<!-- markdownlint-disable MD060 -->

**Версія:** 1.0  
**Дата:** 2025-03  
**Джерело:** [plugins-implementation-plan.md](plugins-implementation-plan.md)

Матриця відповідності «ТЗ → модуль → тести». Оновлюється при кожній зміні плагінів.

---

## 1. Матриця ТЗ → модуль → тести

| ТЗ (план) | Модуль | Файли | Тести |
| --------- | ------ | ----- | ----- |
| **Фаза 1: Coverage** | cdmplugins.coverage | coverage.cdmp, __init__.py, coveragedriver.py, coverageresultviewer.py | Smoke: Run with coverage (Ctrl+Shift+C), вкладка результатів |
| **Фаза 2: Bandit** | cdmplugins.bandit | bandit.cdmp, __init__.py, banditdriver.py (LintDriverBase), banditresultviewer.py | Smoke: Run bandit (Ctrl+Shift+B), JSON output |
| **Фаза 3: pip-audit** | cdmplugins.pipaudit | pipaudit.cdmp, __init__.py, pipauditdriver.py, pipauditresultviewer.py | Smoke: Audit dependencies (Ctrl+Shift+A), вкладка CVE |
| **Фаза 4: Ruff format** | cdmplugins.ruffformat | ruffformat.cdmp, __init__.py, ruffformatdriver.py, ruffformatconfig.py | Smoke: Format (Ctrl+Shift+F), format-on-save (config) |
| **Фаза 5: TODO panel** | cdmplugins.todopanel | todopanel.cdmp, __init__.py, todopaneldriver.py, todopanelviewer.py, todoscanner.py | Smoke: Scan TODO (Ctrl+Shift+O), unit: tests/test_todoscanner.py |
| **Референс: Ruff** | cdmplugins.ruff | ruff.cdmp, __init__.py, ruffdriver.py (LintDriverBase), ruffresultviewer.py | Smoke: Run ruff (Ctrl+Shift+R) |
| **Референс: Mypy** | cdmplugins.mypy | mypy.cdmp, __init__.py, mypydriver.py (LintDriverBase), mypyresultviewer.py | Smoke: Run mypy (Ctrl+Shift+M) |
| **Референс: Pytest** | cdmplugins.pytest | pytest.cdmp, __init__.py, pytestdriver.py, pytestresultviewer.py | Smoke: Run pytest (Ctrl+Shift+T) |
| **Базовий клас** | cdmplugins.lintdriverbase | lintdriverbase.py | Використовується ruff, bandit, mypy |

---

## 2. CI-перевірки

| Перевірка | Команда | Джерело |
| --------- | ------- | ------- |
| Ruff lint | `ruff check codimension cdmplugins` | .github/workflows/ci.yml |
| Ruff format | `ruff format --check codimension cdmplugins` | .github/workflows/ci.yml |
| Mypy | `mypy $(find cdmplugins -name '*.py')` | .github/workflows/ci.yml |
| Smoke | `import codimension; import cdmplugins` | .github/workflows/ci.yml |
| pip-audit | `pip-audit` (smoke job) | .github/workflows/ci.yml |
| Pytest | `pytest tests/` | .github/workflows/ci.yml |

---

## 3. Відповідність плану

- [x] Усі плагіни в `cdmplugins/`
- [x] setup.py оновлено
- [x] requirements.txt оновлено
- [x] Документація оновлена (plugins.md, living-specification.md)
- [x] CI проходить (ruff, mypy)
- [x] Smoke-тест: codimension запускається

---

## 4. Оновлення

При додаванні/зміні плагіна:

1. Додати рядок у матрицю (розд. 1).
2. Оновити setup.py (getPackages, package_data).
3. Оновити requirements.txt (якщо нова залежність).
4. Додати посилання на цей документ у MR.
