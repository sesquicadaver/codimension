# План імплементації плагінів Codimension IDE

**Версія:** 1.0  
**Дата:** 2025-03  
**Статус:** План

---

## 1. Мета та контекст

### 1.1 Ціль
Розширити систему плагінів Codimension інструментами для:

- тестування та покриття коду (Coverage);
- аналізу безпеки (Bandit, pip-audit);
- форматування коду (Ruff format / Black);
- контролю якості (TODO/FIXME panel).

### 1.2 Існуюча архітектура

- **Категорії:** WizardInterface, VersionControlSystemInterface
- **Шаблон плагіна:** `*.cdmp` + `__init__.py` + `*driver.py` + `*resultviewer.py`
- **Розташування:** `cdmplugins/<name>/`
- **Реєстрація:** `setup.py` getPackages(), package_data

### 1.3 Референсні плагіни

| Плагін | Driver | Viewer | Гаряча клавіша |
|--------|--------|--------|----------------|
| ruff   | QProcess, JSON output | QTreeWidget | Ctrl+Shift+R |
| mypy   | QProcess, JSON output | QTreeWidget | Ctrl+Shift+M |
| pytest | QProcess, text parse | QTreeWidget | Ctrl+Shift+T |

---

## 2. Фази імплементації

### Фаза 0: Підготовка (1–2 дні)

- [ ] Створити спільний базовий клас `LintDriverBase` (опціонально) для driver-ів
- [ ] Перевірити сумісність з CI (ruff, mypy у venv)
- [ ] Оновити Living Specification: матриця ТЗ → модуль → тести

### Фаза 1: Coverage (pytest-cov) — 3–5 днів ✅
**Пріоритет:** Високий. Потрібен для CI та Living Specification.

| Крок | Опис | Результат |
|------|------|-----------|
| 1.1 | Створити `cdmplugins/coverage/` | coverage.cdmp, __init__.py ✅ |
| 1.2 | CoverageDriver: `pytest --cov --cov-report=json` | JSON з coverage ✅ |
| 1.3 | CoverageResultViewer: дерево файлів + % покриття | Вкладка в bottom panel ✅ |
| 1.4 | Інтеграція з pytest: опція "Run with coverage" | Кнопка/меню (Ctrl+Shift+C) ✅ |
| 1.5 | Додати в setup.py, requirements.txt | pytest-cov ✅ |

**Файли:**

```
cdmplugins/coverage/
├── coverage.cdmp
├── __init__.py
├── coveragedriver.py
└── coverageresultviewer.py
```

**Залежності:** pytest (вже є), pytest-cov

---

### Фаза 2: Bandit — 2–3 дні ✅
**Пріоритет:** Високий. Security static analysis.

| Крок | Опис | Результат |
|------|------|-----------|
| 2.1 | Створити `cdmplugins/bandit/` | bandit.cdmp, __init__.py ✅ |
| 2.2 | BanditDriver: `bandit -f json -q <file>` | JSON output ✅ |
| 2.3 | BanditResultViewer: file → severity → message | Аналог ruff/mypy ✅ |
| 2.4 | Гаряча клавіша Ctrl+Shift+B | Меню, тулбар, контекст ✅ |

**Файли:**

```
cdmplugins/bandit/
├── bandit.cdmp
├── __init__.py
├── banditdriver.py
└── banditresultviewer.py
```

**Залежності:** bandit

---

### Фаза 3: pip-audit — 2–3 дні ✅
**Пріоритет:** Високий. Перевірка вразливостей залежностей.

| Крок | Опис | Результат |
|------|------|-----------|
| 3.1 | Створити `cdmplugins/pipaudit/` | pipaudit.cdmp, __init__.py ✅ |
| 3.2 | PipAuditDriver: `pip_audit --format json` | JSON ✅ |
| 3.3 | PipAuditResultViewer: package → vuln → CVE | Вкладка ✅ |
| 3.4 | Контекст: Tools menu, buffer, project dir | Запуск з різних точок ✅ |

**Особливість:** Запуск на рівні проекту/venv, не окремого файлу.

**Залежності:** pip-audit

---

### Фаза 4: Ruff format / Black — 2–3 дні ✅
**Пріоритет:** Середній. Форматування коду.

| Крок | Опис | Результат |
|------|------|-----------|
| 4.1 | Створити `cdmplugins/ruffformat/` | cdmp, __init__.py ✅ |
| 4.2 | FormatDriver: `ruff format` | In-place format ✅ |
| 4.3 | Результат: success/error у status bar | Без окремої вкладки ✅ |
| 4.4 | Опція: format on save (config) | getConfigFunction → None (TODO) |

**Варіант:** Використано ruff format (ruff вже є) — менше залежностей.

---

### Фаза 5: TODO/FIXME Panel — 2–3 дні ✅
**Пріоритет:** Середній. Anti-stub перевірка, Living Spec.

| Крок | Опис | Результат |
|------|------|-----------|
| 5.1 | Створити `cdmplugins/todopanel/` | todopanel.cdmp, __init__.py ✅ |
| 5.2 | Сканування проекту: grep TODO, FIXME, XXX, HACK | Регулярні вирази ✅ |
| 5.3 | TodoPanelViewer: file:line → текст | Дерево, клік → goto ✅ |
| 5.4 | Оновлення при збереженні / таймер | Сигнали IDE ✅ |
| 5.5 | Фільтри: TODO only, FIXME only | Toolbar ✅ |

**Реалізація:** Без зовнішніх залежностей (вбудований пошук).

**Файли:**

```
cdmplugins/todopanel/
├── todopanel.cdmp
├── __init__.py
├── todopaneldriver.py
├── todopanelviewer.py
└── todoscanner.py
```

---

## 3. Порядок виконання

```
Фаза 0 (підготовка)
    ↓
Фаза 1 (Coverage)  ← почати тут
    ↓
Фаза 2 (Bandit)
    ↓
Фаза 3 (pip-audit)
    ↓
Фаза 4 (Ruff format)
    ↓
Фаза 5 (TODO panel)
```

**Паралелізація:** Фази 2 і 3 можна виконувати паралельно після Фази 1.

---

## 4. Віртуальне середовище проекту

Опціонально в Project Properties можна вказати **Python interpreter (venv)** — шлях до venv-директорії або виконуваного Python. Якщо вказано, плагіни (ruff, mypy, pytest, coverage, bandit, pip-audit, ruff format) використовують цей інтерпретатор для аналізу замість системного.

- Порожнє поле = використовується Python IDE (sys.executable).
- Підтримуються: venv/bin/python, venv/Scripts/python.exe, або шлях до Python.

---

## 5. Технічні вимоги

### 5.1 Структура кожного плагіна

- Наслідування `WizardInterface`
- `activate()` / `deactivate()` з коректним cleanup
- `isIDEVersionCompatible(ideVersion)` — перевірка версії
- Меню: Tools → <Plugin>, buffer context, file context
- Вкладка в `sideBars['bottom']` (де доречно)
- Гаряча клавіша (унікальна)

### 5.2 Оновлення setup.py

```python
# getPackages()
'cdmplugins.coverage',
'cdmplugins.bandit',
'cdmplugins.pipaudit',
'cdmplugins.ruffformat',  # або black
'cdmplugins.todopanel',

# package_data
('cdmplugins.coverage', 'cdmplugins/coverage/'),
('cdmplugins.bandit', 'cdmplugins/bandit/'),
...
```

### 5.3 Оновлення requirements.txt

```
pytest-cov>=4.0.0
bandit>=1.7.0
pip-audit>=2.0.0
# ruff format — ruff вже є
```

### 5.4 Гарячі клавіші (пропозиція)

| Плагін   | Клавіша        |
|----------|----------------|
| Coverage | Ctrl+Shift+C    |
| Bandit   | Ctrl+Shift+B    |
| pip-audit| Ctrl+Shift+A    |
| Format   | Ctrl+Shift+F    |
| TODO     | Ctrl+Shift+O    |

---

## 6. Тестування

### 6.1 Per-plugin

- Запуск плагіна на тестовому файлі
- Перевірка вкладки результатів
- Перевірка меню та гарячих клавіш
- Deactivate без падіння

### 6.2 Інтеграційне

- Усі плагіни активні одночасно
- Перемикання вкладок
- Запуск з різних контекстів (файл, директорія, проект)

### 6.3 CI

- `pip install -e .` у venv
- Запуск codimension, перевірка завантаження плагінів
- ruff, mypy на коді плагінів

---

## 6. Документація

- [ ] Оновити `doc/plugins/plugins.md` — перелік нових плагінів
- [ ] Додати опис кожного плагіна (короткий)
- [ ] Оновити ChangeLog при кожному релізі
- [ ] Living Specification: ТЗ → модуль → тест

---

## 7. Ризики та обмеження

| Ризик | Мітигація |
|-------|-----------|
| Конфлікт гарячих клавіш | Перевірка існуючих біндингів |
| pip-audit без JSON | Парсинг text output |
| Coverage тільки з pytest | Документувати обмеження |
| Bandit повільний на великих проектах | Запуск у фоні, можливість скасування |

---

## 8. Критерії готовності

- [ ] Усі плагіни в `cdmplugins/`
- [ ] setup.py оновлено
- [ ] requirements.txt оновлено
- [ ] Документація оновлена
- [ ] CI проходить (ruff, mypy)
- [ ] Smoke-тест: codimension запускається, плагіни активуються
