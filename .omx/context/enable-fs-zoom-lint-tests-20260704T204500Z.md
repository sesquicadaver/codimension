# Context: enable-fs-zoom-lint-tests

**Task statement:** Autopilot cycle 5 — увімкнути FS smart zoom (відкритий TODO) і додати unit-тести для lint driver `parseOutput`.

**Desired outcome:**
- Користувач може дійти до рівня smart zoom 4 (dependencies / FS view)
- Немає debug `print()` у production path
- CI: нові тести для ruff/bandit/mypy parseOutput + узгодженість zoom constants
- TODO_FIXME / living-spec / ChangeLog оновлені

**Known facts:**
- `flowuiwidget.py:89-90` тимчасово обмежує `SMART_ZOOM_MAX` до `SMART_ZOOM_CLASS_FUNC`
- `__processFS()` повністю реалізований (DepsVirtualCanvas, collectImportResolutions)
- `Settings.MAX_SMART_ZOOM = 4` уже відповідає `SMART_ZOOM_FS`
- `__processFS` містить `print(deps)` — debug залишок
- Lint drivers: ruff/bandit/mypy мають JSON `parseOutput`, без unit-тестів
- CI зелений: 25 pytest, ruff, mypy, pip-audit

**Constraints:**
- Лише venv; без docker (не чіпали web stack)
- Мінімальний diff; не чіпати watchpoints (занадто багато stub-коду)
- Українська в комунікації; autopilot → commit+push після clean review

**Unknowns:** Чи потрібен QApplication для імпорту flowuiwidget у тестах.

**Touchpoints:**
- `codimension/editor/flowuiwidget.py`
- `tests/test_flowuiwidget.py` (new)
- `tests/test_lint_drivers.py` (new)
- `tests/conftest.py`
- `TODO_FIXME.md`, `doc/plugins/living-specification.md`, `ChangeLog`
