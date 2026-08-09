# Fork Status

> **Мова / Language:** Українська | [English](FORK.en.md)

Цей проєкт — **активний форк** [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).

**Репозиторій:** https://github.com/sesquicadaver/codimension  
**Версія:** 4.11.0 (`codimension/cdmverspec.py`; канал `release_channel`, default `stable`)  
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
- **Project VENV (T140/T141):** VENV… / Update VENV…; status bar **Env:**; re-analyze; unresolved pip opt-in

### Плагіни (cdmplugins/)

Ruff, Mypy, Pytest, Coverage, Bandit, pip-audit, Ruff format, TODO panel, **Git** (status, commit, push, pull, branch, Create/View PR через `gh`).

### Debugger та пошук

- Watchpoints: UI, edit dialog, remote sync з debuggee
- Greenlet `settrace` — відстеження greenlet-контекстів у debugger
- Occurrences search redo (`searchAgain` / `canRedo`)
- Offscreen debugger e2e + nightly full-IDE smoke (T100–T130)

### Headless core / аналіз (R100+)

- `ExecutionTarget`: local / Docker / SSH / Kubernetes MVP
- SymbolIndex, DependencyGraph, MetricProvider, OverlayLayer, risk score
- CFG model + taint MVP; AI context + flag-gated explain/suggest (`ai_ui` / `CDM_AI_UI`)
- Overlays: env / deps heat / deploy hints; update check + verified download (без auto-apply)
- Feature flags: `~/.codimension3/feature_flags.json`

### Інше

- FS smart zoom (рівень 4) у flow UI
- mistune 3.x (`utils/md.py`), pip-audit без CVE-ignore
- CI: ruff + mypy на `codimension` і `cdmplugins`, pytest matrix 3.10–3.13, wheel, offscreen GUI smoke, pip-audit (лічильник тестів — лише в CI)

### UX

- Без автозавантаження останнього проєкту при старті (швидкий запуск)

### Стан плану

Лінійна черга майже завершена (~95%). Відкрито: **R175** (safe-mode). Відкладено: R180–R182. Див. [ROADMAP.uk.md](ROADMAP.uk.md).

## Встановлення

Лише з вихідного коду — див. [README.md](README.md) та [doc/INSTALL.md](doc/INSTALL.md).

## Ліцензія

GPL v3. Збережено всі copyright-нотатки оригіналу. Див. [LICENSE](LICENSE) та [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md).

## Документація

- [doc/README.md](doc/README.md) — індекс документації
- [ROADMAP.md](ROADMAP.md) — довгостроковий план
- [doc/plugins/living-specification.md](doc/plugins/living-specification.md) — матриця ТЗ → модуль → тести
- [TODO_FIXME.md](TODO_FIXME.md) — відомі проблеми
