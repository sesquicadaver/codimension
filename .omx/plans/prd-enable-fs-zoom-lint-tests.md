# PRD: Enable FS Smart Zoom + Lint Driver Tests

## Goal
Зняти тимчасове обмеження smart zoom і закріпити поведінку тестами.

## Scope

### In
1. Видалити override `SMART_ZOOM_MAX = SMART_ZOOM_CLASS_FUNC` у `flowuiwidget.py`
2. Прибрати `print(deps)` з `__processFS`
3. Тести:
   - `SMART_ZOOM_MAX == SMART_ZOOM_FS == Settings.MAX_SMART_ZOOM`
   - `RuffDriver.parseOutput`, `BanditDriver.parseOutput`, `MypyDriver.parseOutput` на sample JSON
4. Оновити `TODO_FIXME.md`, `living-specification.md`, `ChangeLog`

### Out
- Debugger watchpoints (EditWatchpointDialog, `__sendWatchpoints`)
- Greenlets debugger extension
- Повний e2e FS zoom UI

## Acceptance criteria
- [ ] Zoom level 4 доступний (SMART_ZOOM_MAX == 4)
- [ ] Немає `print()` у `__processFS`
- [ ] `pytest tests/` — усі pass (≥30 тестів)
- [ ] `ruff check` / `ruff format --check` pass
- [ ] `mypy cdmplugins` pass

## Verification
```bash
ruff check codimension cdmplugins tests
ruff format --check codimension cdmplugins tests
mypy $(find cdmplugins -name '*.py')
pytest tests/ -v
```

## Risks
- FS view може мати edge-case баги при великих графах — прийнятно; раніше був прихований штучно.
