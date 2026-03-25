# Codimension (Modern Fork)

Codimension — це інструмент для **структурного аналізу Python-коду** з графічним представленням (CFG — control flow graph), який дозволяє бачити логіку виконання коду під час редагування.

Цей репозиторій є **активним форком** оригінального проєкту Codimension (2020), модернізованим для сучасного Python та подальшого розвитку.

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

## ВАРІАНТ 1 — з репозиторію (рекомендовано)

```bash
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt

Запуск:

python codimension.py


---

ВАРІАНТ 2 — через pip

❗ Не рекомендовано для цього форку

pip install codimension

Це встановить стару версію (2020), а не цей форк.


---

Робота з середовищами (Environment)

Проект підтримує прив’язку до Python-середовища (venv), яке використовується для:

коректного import resolution

уникнення false-positive (dead code, unresolved imports)

запуску інструментів (lint, tests, typing)


⚠️ Функціональність ще не завершена.

Планується підтримка:

local venv

Docker

SSH/remote

Kubernetes (пізніше)



---

Архітектура (спрощено)

Code
 → AST
 → CFG
 → Metrics
 → Overlay
 → UI

Майбутній напрям:

Core (analysis engine)
 + Execution targets (venv/docker/ssh)
 + Plugins
 + AI layer


---

Розробка

Структура

codimension/      — основний код
cdmplugins/       — плагіни
doc/              — документація
resources/        — UI ресурси
tests/            — тести


---

Запуск тестів

pytest


---

Лінтинг

ruff check .


---

Ліцензія

Проект ліцензований під GPL v3 (успадковано від оригінального проекту).

⚠️ Робота з приведення форку до повної відповідності ліцензії ще триває.


---

Важливі зауваження

Це не production-ready IDE

Це інструмент для аналізу коду, який активно розвивається

Основний фокус — графічне розуміння логіки, а не заміна VS Code / PyCharm



---

Roadmap (скорочено)

Python 3.10+ стабілізація

Модульна архітектура

Environment-aware аналіз

Dependency discovery

Overlay system (complexity / coverage / runtime)

Graph engine оптимізація

Remote execution

Plugin ecosystem

AI (graph-aware)



---

Посилання

Оригінальний проект: https://github.com/SergeySatskiy/codimension

Цей форк: https://github.com/sesquicadaver/codimension



---

Внесок

PR і issue вітаються.

Перед внесенням змін:

переконайтесь, що не порушується існуюча поведінка (tests)

дотримуйтесь модульної архітектури

не змішуйте UI і core



---

Підсумок

Це проект, що еволюціонує з IDE у:

> інструмент глибокого структурного аналізу Python-коду з графічною інтерпретацією