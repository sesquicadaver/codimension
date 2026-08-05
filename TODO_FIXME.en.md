# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-05 (audit master@1dfb3a1d / PR #23)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (audit 2026-08-05 @ 1dfb3a1d)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| B01 / B02 / C01 / D01 | VENV identity/UUID/destination/base combo | P0–P1 | ✅ |
| D03 | Redirected run/debug/profile argv + `shell=False` | P1 | ✅ partial (redirected) |
| E01 | Custom-terminal `${prog}` argv embedding / quoting | P1 | ✅ launcher path + JSON argv |
| E02 | Custom-terminal Profile = bare Run (no cProfile) | P1 | ✅ `python -m cProfile`; block trailing `&` |
| D02 | Initial VENV create without rollback | P1 | 🔓 OPEN |
| D04 | CML lost inside ordinary comment clusters | P1 | 🔓 OPEN |
| D05 | Encoding cookie on line 2 can be skipped | P1 | 🔓 OPEN |
| D06 | Side comments on multi-line headers not attached | P1 | 🔓 OPEN |
| D07 | Full-IDE smoke ≠ production entrypoint + plugin load | P1 | 🔓 OPEN |
| B03 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN |
| B04 | brief_ast name/colon / assignment positions | P1 | 🔓 OPEN |
| B05 | Comment clusters merge across indent scopes | P1 | 🔓 OPEN |
| B06 | `case` keyword via `rfind` heuristic | P1 | 🔓 OPEN |
| B07 | VENV recreate not transactional; rmtree on GUI thread | P1 | 🔓 OPEN |
| B08 | Full-IDE smoke not PR-blocker / old nightly SHA | P1 | 🔓 OPEN |
| C02 | Interpreter authenticity (probe) / mutable vs read-only | P1 | 🔓 OPEN |
| C03 | Recreate base=`sys.executable` changes Python version | P1 | 🔓 OPEN |
| C04 | Flow UI coupling test skips on any Exception | P1 | 🔓 OPEN |
| B09 | Schema not on all update paths | P2 | 🔓 OPEN |
| B10 | `Settings.flush` not atomic; atomic mode drift | P2 | 🔓 OPEN |
| B11 | Docs drift (README/TODO vs HEAD) | P2 | 🔓 OPEN |
| C05 | Empty UUID not persisted; `uuid1`→`uuid4` | P2 | 🔓 OPEN |
| D08 | No reproducible dependency constraints/lock | P2 | 🔓 OPEN |
| E03 | Release workflow does not verify artifact / trusted publishing | P2 | 🔓 OPEN |

## Infrastructure (fact)

| Topic | State |
|-------|-------|
| **CI** | green on `1dfb3a1d` (200 passed / 2 skipped on 3.12) |
| **Nightly** | ≥1 successful run on old SHA; need run on current HEAD |
| **Living Spec** | keep in sync with B\*/C\*/D\*/E\* |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
