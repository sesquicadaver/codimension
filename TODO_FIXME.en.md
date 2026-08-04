# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-04 (re-audit master@f5196a67 + PR #19)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (audit 2026-08-04 @ f5196a67)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| B01 | VENV identity: `realpath(python)` confuses project venv with IDE | P0 | ✅ venv root vs `sys.prefix` |
| B02 | `.cdm3` uuid path traversal / no `uuid.UUID` | P0 | ✅ canonical UUID + `safe_user_project_dir` |
| B03 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN (was A09) |
| B04 | brief_ast name/colon positions | P1 | 🔓 OPEN (was A08) |
| B05 | Comment clusters merge across indent scopes | P1 | 🔓 OPEN |
| B06 | `case` keyword via `rfind` heuristic | P1 | 🔓 OPEN |
| B07 | VENV recreate not transactional; rmtree on GUI thread | P1 | 🔓 OPEN |
| B08 | Full-IDE smoke nightly-only (0 runs) / formal offscreen | P1 | 🔓 OPEN |
| B09 | Schema not on all update paths | P2 | 🔓 OPEN (was A10) |
| B10 | `Settings.flush` not atomic; atomic mode drift | P2 | 🔓 OPEN (was A11) |
| B11 | Docs drift (README/TODO vs commit) | P2 | 🔓 OPEN |

## Closed from prior audits (confirmed @ f5196a67)

| ID | Topic | Status |
|----|-------|--------|
| A01 | Independent CI jobs + green | ✅ |
| A02–A03 | VENV mutate guards + async QProcess | ✅ (B01 extra identity fix) |
| A04–A05 | brief CF defs; half-open spans / relative imports | ✅ |
| A07 | tokenize char columns + nested trailing | ✅ PR #19 |
| A14 | profgraph drawPixmap | ✅ |

## Infrastructure (fact)

| Topic | State |
|-------|-------|
| **CI** | green on `f5196a67` |
| **Living Spec** | keep in sync with B01–B11 |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
