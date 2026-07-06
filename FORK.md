# Fork Status

Цей проєкт — **активний форк** [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).

**Репозиторій:** https://github.com/sesquicadaver/codimension  
**Версія:** 4.11.0 (`codimension/cdmverspec.py`)  
**Python:** 3.10+ (`pyproject.toml`: `requires-python >= "3.10"`)

## Чому форк

Оригінальний репозиторій не підтримується понад 4 роки. Сайт codimension.org та пов’язані репозиторії (cdm-pythonparser, cdm-flowparser) також не оновлюються.

**Клонувати або завантажувати з оригінального репозиторію немає сенсу** — використовуйте цей форк.  
**Не використовуйте `pip install codimension`** — PyPI містить застарілу upstream-версію, не цей форк.

## Що змінено у форку

### Платформа та парсери

- Підтримка Python 3.10–3.13
- Pure-Python fallback-парсери (`brief_ast`, `flow_ast`) замість C-розширень cdmpyparser/cdmcfparser
- Сумісність з Python 3.12+ (setuptools/distutils shims)

### Аналіз проєкту

- `excludeFromAnalysis` — виключення шляхів з аналізу
- Автоматичне виключення venv з аналізу
- Lazy load для Classes/Functions/Globals
- Tools → Project utilities → Generate requirements file

### Плагіни (cdmplugins/)

Ruff, Mypy, Pytest, Coverage, Bandit, pip-audit, Ruff format, TODO panel, **Git** (MVP: status, commit, push, pull, branch, Create/View PR через `gh`; stash/merge UI — не реалізовано).

### Debugger та пошук (2026-07)

- Watchpoints: UI, edit dialog, remote sync з debuggee
- Greenlet `settrace` — відстеження greenlet-контекстів у debugger
- Occurrences search redo (`searchAgain` / `canRedo`)

### Інше (2026-07)

- FS smart zoom (рівень 4) у flow UI
- mistune 3.x (`utils/md.py`), pip-audit без CVE-ignore
- CI: ruff + mypy на `codimension` і `cdmplugins`, pytest (46 тестів), pip-audit

### UX

- Без автозавантаження останнього проєкту при старті (швидкий запуск)

## Встановлення

Лише з вихідного коду — див. [README.md](README.md) та [doc/INSTALL.md](doc/INSTALL.md).

## Ліцензія

GPL v3. Збережено всі copyright-нотатки оригіналу. Див. [LICENSE](LICENSE) та [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md).

## Документація

- [doc/README.md](doc/README.md) — індекс документації
- [ROADMAP.md](ROADMAP.md) — довгостроковий план
- [doc/plugins/living-specification.md](doc/plugins/living-specification.md) — матриця ТЗ → модуль → тести
- [TODO_FIXME.md](TODO_FIXME.md) — відомі проблеми
