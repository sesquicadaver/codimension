# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-05 (audit master@a2c88921 / PR #28)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (audit @ a2c88921)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| B01 / B02 / C01 / D01 | VENV identity/UUID/destination/base combo | P0–P1 | ✅ |
| D03 | Redirected argv + `shell=False` | P1 | ✅ (redirected) |
| E01 / E02 | Custom-terminal launcher `${prog}` + Profile cProfile | P1 | ✅ |
| E04 / F07 | Stale cleanup symlink traversal under `/tmp` | P1 | ✅ lstat/O_NOFOLLOW + one-shot legacy `/tmp` |
| E04 (normal unlink) | Launcher cleanup before execvp | P1 | ✅ |
| E05 | Profile timeout still shell `&` heuristic; orphan `.done` | P1 | ✅ start deadline + marker cleanup |
| E06 | noexec execute-probe; shell-safe path limits | P1 | ✅ exec probe + DQ-safe paths |
| D02 / B07 | VENV create/recreate without transaction/rollback | P1 | ✅ staging + commit |
| C02 / C03 | Interpreter probe; recreate=`sys.executable` | P1 | 🔓 OPEN |
| B03 | Project scan cancel/join/coalescing | P1 | 🔓 OPEN |
| B04 / B05 / B06 / D04 / D05 / D06 | Parser positions / CML / case / encoding / side comments | P1 | 🔓 OPEN |
| D07 / B08 / C04 | Production startup + plugin load; Flow UI skip | P1 | 🔓 OPEN |
| B11 | Docs drift (TODO/Living Spec/`doc/uk`, docs gate coverage) | P2 | 🔓 OPEN |
| B09 / B10 / C05 | Schema paths / atomic settings / UUID persist | P2 | 🔓 OPEN |
| D08 / E03 / G01 | Constraints / release verify / branch protection | P2 | 🔓 OPEN |

## Infrastructure

| Topic | State |
|-------|-------|
| **CI** | verify latest green Actions on HEAD (no static count in README) |
| **Docs gate** | `python scripts/check_docs.py` (partial: .md links; see B11) |
| **Nightly full-IDE** | weekly, not a PR blocker |
| **Living Spec** | module matrix; no static SHA/test count |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
