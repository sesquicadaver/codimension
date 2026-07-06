# TODO_FIXME — Список виявлених проблем для виправлення

**Дата перевірки:** 2026-07-05  
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
| `codimension/diagram/depsitems.py` | — | Connector на scene для deps-діаграми | ✅ Виправлено 2026-07-04 |

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

| Проблема | Рекомендація |
|----------|--------------|
| **Відсутність тестів** | Базові unit-тести: gitstatusparser, todoscanner, flow_ast, binfiles. Розширити покриття. |
| **mypy** | codimension + cdmplugins у CI | ✅ Виправлено 2026-07-05 |
| **venv** | ruff/mypy не встановлені в .venv. Додати до dev-залежностей. |
| **README vs pyproject** | Вирішено: README оновлено до Python 3.11+ |
| **excludeFromAnalysis, venv exclusion** | Реалізовано: doc/project/project.md, README оновлено |
| **Lazy load Classes/Functions/Globals** | Реалізовано: populateIfNeeded при першому показі вкладки |

## Рекомендації щодо CI

1. `ruff check codimension/` — проходить
2. Додати pytest до dev-залежностей
3. Встановити ruff, mypy в venv для CI
4. Оновити README: Python 3.11+ (відповідно до pyproject.toml)
