# TODO_FIXME — Список виявлених проблем для виправлення

**Дата перевірки:** 2026-07-06  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Критичні (anti-stub перевірка)

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
| **Unit-тести** | 46 тестів у `tests/` (pytest). Розширити CFG snapshot coverage. |
| **mypy** | `codimension` + `cdmplugins` у CI | ✅ 2026-07-05 |
| **ruff/mypy у venv** | У `requirements.txt` | ✅ |
| **README / INSTALL** | Лише встановлення з репозиторію, Python 3.10+ | ✅ 2026-07-06 |
| **excludeFromAnalysis, venv exclusion** | doc/project/project.md | ✅ |
| **Lazy load Classes/Functions/Globals** | populateIfNeeded | ✅ |

## Рекомендації щодо CI

Усі пункти виконано в `.github/workflows/ci.yml`:

1. `ruff check` / `ruff format --check`
2. `mypy` на codimension + cdmplugins
3. `pytest tests/`
4. `pip-audit -r requirements.txt`
5. Smoke: `import codimension; import cdmplugins`

Див. [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
