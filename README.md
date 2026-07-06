# Codimension (Modern Fork)

[![CI](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml/badge.svg)](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPL%20v3-green.svg)](LICENSE)

Codimension — це інструмент для **структурного аналізу Python-коду** з графічним представленням (CFG — control flow graph), який дозволяє бачити логіку виконання коду під час редагування.

**Fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).** Оригінальний проєкт не підтримується понад 4 роки. Цей репозиторій є **активним форком**, модернізованим для сучасного Python (3.10+) та подальшого розвитку.

## Посилання

- **Цей репозиторій** — активний форк для розробки та встановлення
- [Оригінальний проєкт (архів)](https://github.com/SergeySatskiy/codimension) — історичний, не підтримується
- [Технологія та візуалізація](http://codimension.org/documentation/visualization-technology/python-code-visualization.html)
- [CAN-MCP (Codimension ANalizer MCP)](https://github.com/sesquicadaver/CAN-MCP) — Codimension based MCP-сервер
- [Гарячі клавіші](http://codimension.org/documentation/cheatsheet.html)
- **Детальна інструкція з встановлення:** [doc/INSTALL.md](doc/INSTALL.md)
- **Документація проєкту:** [doc/README.md](doc/README.md)
- **Статус форку:** [FORK.md](FORK.md)
- **Roadmap:** [ROADMAP.md](ROADMAP.md)

**Примітка:** Сайт codimension.org та оригінальні репозиторії (cdm-pythonparser, cdm-flowparser) більше не оновлюються. Клонувати або завантажувати з upstream немає сенсу — використовуйте цей форк.

---

# Основні можливості

- Візуалізація control-flow (CFG) у реальному часі
- Синхронізація коду та графа
- Базовий статичний аналіз Python-коду
- Інтеграція інструментів:
  - Ruff (lint/format)
  - Mypy / Pyright (typing)
  - Pytest (тести)
  - Coverage
  - Bandit / pip-audit
- Підтримка роботи з проектами
- Плагінна архітектура (у розвитку)

---

# Статус проекту

⚠️ Проект знаходиться в активній стадії рефакторингу:

- перехід на Python 3.10+
- виділення core-аналізатора
- підготовка до модульної архітектури
- побудова системи environment-aware аналізу

Не всі функції завершені. Поведінка може змінюватися.

---

# Вимоги

- Python: **3.10 – 3.13**
- ОС:
  - Linux (основна підтримка)
  - Windows (експериментально)
  - macOS (експериментально)
- Qt: **PyQt5**

---

# Встановлення

З репозиторію (єдиний підтримуваний спосіб для цього форку):

```bash
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
pip install -e .
```

Запуск:

```bash
codimension
```

Детальніше (Windows, системні залежності): [doc/INSTALL.md](doc/INSTALL.md).

---

# Робота з середовищами (Environment)

Проект підтримує прив’язку до Python-середовища (venv), яке використовується для:

- коректного import resolution
- уникнення false-positive (dead code, unresolved imports)
- запуску інструментів (lint, tests, typing)

⚠️ Функціональність ще не завершена.

Планується підтримка:

- local venv
- Docker
- SSH/remote
- Kubernetes (пізніше)

---

# Архітектура (спрощено)

```text
Code
 → AST
 → CFG
 → Metrics
 → Overlay
 → UI
```

Майбутній напрям:

```text
Core (analysis engine)
 + Execution targets (venv/docker/ssh)
 + Plugins
 + AI layer
```

---

# Розробка

## Структура

```text
codimension/      — основний код
cdmplugins/       — плагіни
doc/              — документація
resources/        — UI ресурси
tests/            — тести
```

## Запуск тестів

```bash
pytest tests/ -v
```

## Лінтинг і типізація

```bash
ruff check codimension cdmplugins
ruff format --check codimension cdmplugins
mypy $(find codimension cdmplugins -name '*.py' ! -path '*/flowui/everything.py')
pip-audit -r requirements.txt
```

Повний чекліст — [CONTRIBUTING.md](CONTRIBUTING.md). Матриця модулів і тестів — [doc/plugins/living-specification.md](doc/plugins/living-specification.md).

---

# Ліцензія

Проект ліцензований під GPL v3 (успадковано від оригінального проєкту).

⚠️ Робота з приведення форку до повної відповідності ліцензії ще триває.

---

# Важливі зауваження

- Це не production-ready IDE
- Це інструмент для аналізу коду, який активно розвивається
- Основний фокус — графічне розуміння логіки, а не заміна VS Code / PyCharm

---

# Roadmap (скорочено)

Повний план: [ROADMAP.md](ROADMAP.md).

- Python 3.10+ стабілізація
- Модульна архітектура
- Environment-aware аналіз
- Dependency discovery
- Overlay system (complexity / coverage / runtime)
- Graph engine оптимізація
- Remote execution
- Plugin ecosystem
- AI (graph-aware)

---

# Внесок

PR і issue вітаються.

Перед внесенням змін:

- переконайтесь, що не порушується існуюча поведінка (tests)
- дотримуйтесь модульної архітектури
- не змішуйте UI і core
- оновлюйте `ChangeLog` і `doc/` при зміні функціоналу

Деталі: [CONTRIBUTING.md](CONTRIBUTING.md).

---

# Підсумок

Це проект, що еволюціонує з IDE у:

> інструмент глибокого структурного аналізу Python-коду з графічною інтерпретацією
