# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-02  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension  
**Лінійний план:** [.omx/plans/linear-remediation-atomic-20260802.md](.omx/plans/linear-remediation-atomic-20260802.md)

## Критичні (anti-stub / коректність ядра) — аудит 2026-08-02

| ID плану | Файл / зона | Опис | Статус |
|----------|-------------|------|--------|
| T010–T018 | `codimension/parsers/brief_ast.py` | brief M1 foundation | ✅ DONE 2026-08-02 |
| T020–T028.C | `flow_ast` + `comment_binder` + Flow UI coupling | M2 Flow Foundation | ✅ DONE 2026-08-02 |
| T003 | `codimension/parsers/source_spans.py` | Спільна byte→char таблиця позицій | ✅ T003 DONE 2026-08-02 |
| T001 | `doc/technology/parser-contract.md` | Parser contract normative | ✅ DONE 2026-08-02 |
| T004–T006 | `tests/conformance/` | Conformance harness + CFG goldens | ✅ DONE 2026-08-02 |
| T029 | `tests/conformance/differential-report.md` | C-ext відсутній → explicit skip | ✅ SKIPPED (documented) |
| T034–T035 | `cdmplugins/mypy/mypydriver.py` | Очікує `{"files":...}`, mypy дає JSONL | 🔴 TODO |
| T030–T033 | `cdmplugins/lintdriverbase.py` + drivers | Порожній `QProcessEnvironment()`; блокуючий `kill`/`waitForFinished` | 🔴 TODO |
| T040–T041 | `cdmplugins/git/gitconfig.py` | GitHub PAT plaintext у `~/.codimension3/git.plugin.conf` | 🔴 TODO |
| T042–T043 | `codimension/utils/project.py` | Неатомарний `.cdm3`; немає schema validation | 🔴 TODO |
| T050–T051 | `codimension/utils/project.py` | Basename-only exclusions; необмежений symlink traversal | 🔴 TODO |
| T060–T067 | `pyproject.toml` / CI | Немає `[project.dependencies]`; CI ≠ заявлена матриця 3.10–3.13 | 🔴 TODO |
| T070–T073 | bootstrap / imports | `sys.path` alias; dual-import singletons | 🟠 TODO |

## Критичні (anti-stub перевірка) — раніше

| Файл | Рядок | Опис | Статус |
|------|-------|------|--------|
| `codimension/utils/binfiles.py` | — | hexdump через subprocess | ✅ Виправлено 2026-07-04 |
| `codimension/editor/flowuiwidget.py` | — | FS smart zoom enabled (SMART_ZOOM_MAX) | ✅ Виправлено 2026-07-04 |
| `codimension/utils/md.py` | — | mistune 3.x migration | ✅ Виправлено 2026-07-04 |
| `codimension/search/occurrencesprovider.py` | — | searchAgain stub (`pass`) | ✅ Виправлено 2026-07-05 |

## Виправлено (2026-07-04)

| Файл | Опис |
|------|------|
| `codimension/parsers/flow_ast.py` | `from X import` — `_pos(node.module)` замінено на span з source |
| `codimension/ui/editorsmanager.py` | `onHighlightInFS` — інвертована умова |
| `codimension/diagram/depsitems.py` | Connector на scene для deps-діаграми |

## TODO з явною позначкою

| Файл | Рядок | Опис |
|------|-------|------|
| `codimension/debugger/bpwp.py` | — | WatchPointViewer enabled in debugger panel | ✅ Виправлено 2026-07-05 |
| `codimension/debugger/server.py` | — | `__sendWatchpoints` sync to debuggee | ✅ Виправлено 2026-07-05 |
| `codimension/debugger/client/threadextension_cdm_dbg.py` | — | greenlet.settrace debugger extension | ✅ Виправлено 2026-07-05 |

## Заглушки `pass` (потребують перевірки)

- **flowui/everything.py** — демо-файл для flow UI, ігнорується ruff
- **runmanager.py, mainstatusbar.py** — `pass` у except/empty handlers
- **variablesbrowser.py, notused.py, brief_ast.py** — `pass` у обробниках
- **vcsannotateviewer.py, classesviewer.py** — `pass` у методах
- **profgraph.py, importsdgm.py, asyncfile_cdm_dbg.py** — `pass` у обробниках
- **wpointviewer.py, editorsmanager.py** — `pass` у обробниках
- **resultprovideriface.py** — абстрактний інтерфейс
- **profiletest.py** — тестовий файл профілювання

## Інфраструктура

| Проблема | Статус |
|----------|--------|
| **Unit-тести** | 46 тестів у `tests/`. CFG snapshot / parser conformance — у плані T004–T028. |
| **mypy** | `codimension` + `cdmplugins` у CI | ✅ 2026-07-05 (парсер виводу mypy — T034) |
| **ruff/mypy у venv** | У `requirements.txt` | ✅ |
| **README / INSTALL** | Заявлена CI-матриця розходиться з workflow — T067 |
| **excludeFromAnalysis** | Path-aware exclusions — T050 |
| **Lazy load Classes/Functions/Globals** | populateIfNeeded | ✅ |

## Рекомендації щодо CI

Поточний `.github/workflows/ci.yml` (факт 2026-08-02):

1. Lint: Python 3.10–3.12 (не 3.13)
2. Pytest/smoke: лише 3.11
3. Немає wheel build / clean install / offscreen GUI

Цільовий стан — задачі **T063–T066**. Жива матриця модулів: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
