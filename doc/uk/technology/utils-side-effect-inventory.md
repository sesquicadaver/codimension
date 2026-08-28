> **Мова / Language:** Українська | [English](../../technology/utils-side-effect-inventory.md)

# Інвентар side-effect у `utils` (R195 / A223.a)

`codimension.utils` — не чистий шар хелперів: частина модулів тягне Qt, UI
діалоги або менеджер плагінів. R195 фіксує інвентар і **закриває відкриту
підлогу** меж: нові ребра `utils → ui|plugins|qt` падають у CI, якщо їх немає
в grandfather-списку.

Gate: `python scripts/check_module_boundaries.py`  
Allowlist: `UTILS_LEGACY_EDGES` у `scripts/check_module_boundaries.py`  
Тести: `tests/test_module_boundaries.py`

## Підлога utils (R195)

| Імпортер | Дозволені іменовані шари |
| -------- | ------------------------ |
| utils | core, infrastructure, app |
| utils (лише legacy) | ui / plugins / qt через `UTILS_LEGACY_EDGES` |

Ціль (далі по roadmap): зменшити legacy-мапу до порожньої (R196+ hotspots).

## Grandfathered модулі

| Модуль | Legacy-ребра | Нотатки щодо ефектів |
| ------ | ------------ | -------------------- |
| `utils/colorfont.py` | ui | Типи кольору/шрифту через `ui.qt` |
| `utils/fileutils.py` | ui | `QImageReader` для sniff зображень |
| `utils/globals.py` | plugins | Lazy `CDMPluginManager`; також `app.services` (дозволено підлогою) |
| `utils/pixmapcache.py` | ui | Кеш `QIcon` / `QPixmap` |
| `utils/plantumlcache.py` | ui | Воркер `QObject` / `QThread` |
| `utils/project.py` | ui, qt | Сигнали + прямі хелпери `PyQt5` |
| `utils/runmanager.py` | ui | Run UI (`ui.runparamsdlg`) + типи Qt |
| `utils/settings.py` | ui | `QObject` / сигнали / `QDir` |
| `utils/skin.py` | ui | `QColor` / `QFont` у моделі скіна |
| `utils/ssh_project_runtime.py` | ui | Lazy `QTimer` для колбеків UI-потоку |
| `utils/watcher.py` | qt | Прямий `PyQt5.QtCore` filesystem watcher |
| `utils/webresourcecache.py` | ui | Завантажувач `QObject` / `QThread` |

**R196:** `utils/versions.py` прибрано з legacy-мапи — версія Qt інжектиться
з `ui.about` через `getComponentInfo(qt_version=…)`.

## Політика

- **Не розширювати** `UTILS_LEGACY_EDGES` під нові фічі — інвертувати залежність
  (перенести Qt/UI у `ui` / `app`), див. R196.
- Видалення grandfathered-імпорту вимагає прибрати запис allowlist у тому ж PR
  (gate падає на застарілих записах).
