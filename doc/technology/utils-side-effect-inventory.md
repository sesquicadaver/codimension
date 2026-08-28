> **Language / Мова:** English | [Українська](../uk/technology/utils-side-effect-inventory.md)

# Utils side-effect inventory (R195 / A223.a)

`codimension.utils` is not a pure helper layer: several modules pull Qt, UI
dialogs, or the plugin manager. R195 records that inventory and **closes the
open boundary floor** so new `utils → ui|plugins|qt` edges fail CI unless they
are explicitly grandfathered.

Gate: `python scripts/check_module_boundaries.py`  
Allowlist: `UTILS_LEGACY_EDGES` in `scripts/check_module_boundaries.py`  
Tests: `tests/test_module_boundaries.py`

## Enforced utils floor (R195)

| Importer | May import (named layers) |
| -------- | ------------------------- |
| utils | core, infrastructure, app |
| utils (legacy only) | ui / plugins / qt via `UTILS_LEGACY_EDGES` |

Target (later roadmap): shrink the legacy map to empty (R196+ hotspots).

## Grandfathered modules

| Module | Legacy edges | Side-effect notes |
| ------ | ------------ | ----------------- |
| `utils/colorfont.py` | ui | Qt color/font types via `ui.qt` |
| `utils/fileutils.py` | ui | `QImageReader` for image sniffing |
| `utils/globals.py` | plugins | Lazy `CDMPluginManager`; also `app.services` (allowed by floor) |
| `utils/pixmapcache.py` | ui | `QIcon` / `QPixmap` cache |
| `utils/plantumlcache.py` | ui | `QObject` / `QThread` worker |
| `utils/project.py` | ui, qt | Signals + direct `PyQt5` thread/app helpers |
| `utils/runmanager.py` | ui | Run UI (`ui.runparamsdlg`) + Qt types |
| `utils/settings.py` | ui | `QObject` / signals / `QDir` |
| `utils/skin.py` | ui | `QColor` / `QFont` in skin model |
| `utils/ssh_project_runtime.py` | ui | Lazy `QTimer` for UI-thread callbacks |
| `utils/versions.py` | ui | Lazy `QT_VERSION_STR` |
| `utils/watcher.py` | qt | Direct `PyQt5.QtCore` filesystem watcher |
| `utils/webresourcecache.py` | ui | `QObject` / `QThread` downloader |

## Policy

- **Do not grow** `UTILS_LEGACY_EDGES` for new features — invert the dependency
  (move Qt/UI into `ui` / `app`) instead (see R196).
- Removing a grandfathered import requires deleting that path’s allowlist entry
  in the same PR (gate fails on stale entries).
