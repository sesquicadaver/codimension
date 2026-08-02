# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-03  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Завершений аудит 2026-08 (T001–T141)

Усі пункти лінійного remediation і follow-up VENV/env — **DONE**. Деталі — [ChangeLog](ChangeLog), матриця — [doc/plugins/living-specification.md](doc/plugins/living-specification.md).

| Блок | Статус |
|------|--------|
| Parsers / conformance (T001–T029) | ✅ DONE (T029 SKIPPED — C-ext відсутній) |
| Tooling / credentials / project scan (T030–T052) | ✅ DONE |
| Packaging / CI / bootstrap / core (T060–T085) | ✅ DONE |
| Debugger GUI e2e (T100–T130) | ✅ DONE (T130 — nightly, не PR-blocker) |
| Project VENV + analysis env (T140–T141) | ✅ DONE |

## Заглушки `pass` (потребують перевірки)

- **flowui/everything.py** — демо-файл для flow UI, ігнорується ruff
- **runmanager.py, mainstatusbar.py** — `pass` у except/empty handlers
- **variablesbrowser.py, notused.py, brief_ast.py** — `pass` у обробниках
- **vcsannotateviewer.py, classesviewer.py** — `pass` у методах
- **profgraph.py, importsdgm.py, asyncfile_cdm_dbg.py** — `pass` у обробниках
- **wpointviewer.py, editorsmanager.py** — `pass` у обробниках
- **resultprovideriface.py** — абстрактний інтерфейс
- **profiletest.py** — тестовий файл профілювання

## Інфраструктура (факт)

| Тема | Стан |
|------|------|
| **Unit-тести** | `pytest tests/` — **173** тестів (matrix 3.10–3.13 у CI) |
| **mypy / ruff** | `codimension` + `cdmplugins` у CI; інструменти у `requirements.txt` |
| **CI** | lint + pytest; wheel+`pip check`; offscreen GUI smoke; pip-audit; T072/T085 gates; debugger_session step |
| **Lazy load Classes/Functions/Globals** | `populateIfNeeded` ✅ |

Жива матриця модулів: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
