# Codimension

> **Мова / Language:** Українська | [English](README.en.md)

[![CI](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml/badge.svg)](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPL%20v3-green.svg)](LICENSE)

**Експериментальна Python IDE** з текстовим редактором і **діаграмою потоку керування** (flow diagram), що оновлюється під час редагування коду. Версія форку: **4.11.0**.

Це **активний форк** [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Оригінал не підтримується понад 4 роки; `pip install codimension` з PyPI — застаріла upstream-версія, не цей репозиторій.

## Що є зараз

- Редагування Python-файлів і **синхронізована flow-діаграма** (control flow)
- Діаграми імпортів, класів, залежностей; dead code (vulture), складність (radon), pyflakes у редакторі
- **Проєкти** (`.cdm3`): `excludeFromAnalysis`, без автозавантаження останнього проєкту при старті
- **Project VENV (T140/T141):** Tools → Project utilities → **VENV…** / **Update VENV…**; status bar **Env:** (`project` / `session` / `auto` / `IDE` / `broken`); re-analyze після зміни env
- **Парсери:** pure-Python `brief_ast` / `flow_ast` на Python 3.10+ (без cdmpyparser/cdmcfparser)
- **Вбудовані плагіни** (`cdmplugins/`): Ruff, Ruff format, Mypy, Pytest, Coverage, Bandit, pip-audit, TODO panel, Git (MVP)
- **Debugger:** breakpoints, watchpoints (UI + sync), greenlet-контексти; nightly full-IDE smoke (T130)
- **CI:** незалежні ruff / format / mypy / pytest (~**189** тестів) matrix **3.10–3.13**, wheel+`pip check`, offscreen GUI smoke, pip-audit

## Обмеження (чесно)

- Не production-ready IDE; орієнтир — аналіз і візуалізація коду, не заміна VS Code / PyCharm
- Git-плагін — MVP (без stash/merge UI); PR через `gh` CLI
- Environment-aware аналіз (Docker / SSH / K8s) — **не реалізовано**; локальний venv — через Project Properties або Tools → **VENV…** (async QProcess + mutate guards)
- Авто-setup venv на open — **немає**; unresolved packages для pip — opt-in; див. відкриті пункти аудиту в [TODO_FIXME.md](TODO_FIXME.md)
- Не production-ready analyzer: залишкові gaps — [TODO_FIXME.md](TODO_FIXME.md) B03–B11
- Довгострокові плани — [ROADMAP.md](ROADMAP.md), не поточний стан

## Вимоги

- Python **3.10–3.13** (CI: 3.10, 3.11, 3.12, 3.13)
- **PyQt5**, Linux (основна платформа); Windows / macOS — експериментально

## Встановлення

Лише з вихідного коду:

```bash
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
pip install -e .
codimension
```

Деталі: [doc/INSTALL.md](doc/INSTALL.md).

## Розробка

```bash
pytest tests/ -v
ruff check codimension cdmplugins
ruff format --check codimension cdmplugins
mypy $(find codimension cdmplugins -name '*.py' ! -path '*/flowui/everything.py')
pip-audit -r requirements.txt
```

Структура: `codimension/` (IDE), `cdmplugins/` (плагіни), `tests/`, `doc/`.

Чекліст для PR — [CONTRIBUTING.md](CONTRIBUTING.md). Матриця модулів і тестів — [doc/plugins/living-specification.md](doc/plugins/living-specification.md).

## Документація

| | |
| --- | --- |
| [doc/BILINGUAL.md](doc/BILINGUAL.md) | Двомовна документація (політика) |
| [doc/README.md](doc/README.md) / [doc/en/README.md](doc/en/README.md) | Індекс документації (UK / EN) |
| [FORK.md](FORK.md) / [FORK.en.md](FORK.en.md) | Зміни форку |
| [ROADMAP.uk.md](ROADMAP.uk.md) / [ROADMAP.md](ROADMAP.md) | Довгостроковий план |
| [TODO_FIXME.md](TODO_FIXME.md) / [TODO_FIXME.en.md](TODO_FIXME.en.md) | Відомі проблеми |
| [ChangeLog](ChangeLog) | Історія змін |

Зовнішні (архів): [codimension.org](http://codimension.org) — не оновлюється. Актуальний MCP-застосунок: [CAN-MCP](https://github.com/sesquicadaver/CAN-MCP).

## Ліцензія

GPL v3. Модифікована версія — див. [FORK.md](FORK.md), [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md).
