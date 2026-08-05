# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-05 (audit master@550ddb4b / PR #24)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (audit @ 550ddb4b)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| B01 / B02 / C01 / D01 | VENV identity/UUID/destination/base combo | P0–P1 | ✅ |
| D03 | Redirected argv + `shell=False` | P1 | ✅ (redirected) |
| E01 / E02 | Custom-terminal launcher `${prog}` + Profile cProfile | P1 | ✅ |
| E04 | Launcher temp dirs / argv.json never cleaned | P1 | ✅ unlink before execvp + stale cleanup |
| E05 | Profile completion tied to terminal / `&` heuristic | P1 | 🔓 OPEN |
| E06 | Launcher POSIX-only (`env python3`, path regex) | P1 | 🔓 OPEN |
| D02 / B07 | VENV create/recreate without transaction/rollback | P1 | 🔓 OPEN |
| C02 / C03 | Interpreter probe; recreate=`sys.executable` | P1 | 🔓 OPEN |
| B03 | Project scan cancel/join/coalescing | P1 | 🔓 OPEN |
| B04 / B05 / B06 / D04 / D05 / D06 | Parser positions / CML / case / encoding / side comments | P1 | 🔓 OPEN |
| D07 / B08 / C04 | Production startup + plugin load; Flow UI skip | P1 | 🔓 OPEN |
| B11 | Docs drift (README/INSTALL/Living Spec) | P1 | ✅ rewrite + `scripts/check_docs.py` |
| B09 / B10 / C05 | Schema paths / atomic settings / UUID persist | P2 | 🔓 OPEN |
| D08 / E03 / G01 | Constraints / release verify / branch protection | P2 | 🔓 OPEN |

## Infrastructure

| Topic | State |
|-------|-------|
| **CI** | verify latest green Actions on HEAD (no static count in README) |
| **Docs gate** | `python scripts/check_docs.py` |
| **Nightly full-IDE** | weekly, not a PR blocker; need a run on current HEAD |
| **Living Spec** | module matrix; no static SHA/test count |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
