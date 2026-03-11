# TODO_FIXME — Список виявлених проблем для виправлення

**Дата перевірки:** 2025-03-11

## Критичні (anti-stub перевірка)

| Файл | Рядок | Опис |
|------|-------|------|
| `codimension/utils/binfiles.py` | 33 | **TODO:** Реалізувати hexdump через subprocess коли hexdumpAvailable — функція завжди повертає `None` |
| `codimension/editor/flowuiwidget.py` | 89 | **TODO:** Till FS zoom is implemented — тимчасове перевизначення SMART_ZOOM_MAX |

## TODO з явною позначкою

| Файл | Рядок | Опис |
|------|-------|------|
| `codimension/debugger/bpwp.py` | 48 | **TODO: temporary** — WatchPointViewer приховано |
| `codimension/debugger/client/threadextension_cdm_dbg.py` | 249 | **TODO:** Implement the debugger extension for greenlets |

## Заглушки `pass` (потребують перевірки)

- **wizardiface.py** — `pass` у абстрактних методах інтерфейсу (прийнятно)
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
| **Відсутність тестів** | Немає pytest/unittest у проекті. Додати CI з тестами. |
| **mypy** | Не знаходить .py файли (можлива конфігурація). Перевірити mypy. |
| **venv** | ruff/mypy не встановлені в .venv. Додати до dev-залежностей. |
| **README vs pyproject** | README: Python 3.5–3.9; pyproject: >=3.11. Розбіжність. |

## Рекомендації щодо CI

1. `ruff check codimension/` — проходить
2. Додати pytest до dev-залежностей
3. Встановити ruff, mypy в venv для CI
4. Оновити README: Python 3.11+ (відповідно до pyproject.toml)
