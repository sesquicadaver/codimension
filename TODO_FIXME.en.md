# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-05 (audit master@8c60ad5c / PR #21)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (audit 2026-08-05 @ 8c60ad5c)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| B01 | VENV identity: `realpath(python)` confuses project venv with IDE | P0 | ✅ |
| B02 | `.cdm3` uuid path traversal / no `uuid.UUID` | P0 | ✅ |
| C01 | Create VENV without destination guard | P0 | ✅ `validateVenvDestination` sync+QProcess |
| D01 | Base interpreter combo: Browse/`setEditText` ignored (`currentData`) | P1 | ✅ `selectedBaseInterpreter` |
| D02 | Initial VENV create without rollback (partial dir blocks retry) | P1 | 🔓 OPEN |
| D03 | Run/debug/profile args via `shell=True` break argv boundaries | P1 | 🔓 OPEN |
| D04 | CML lost inside ordinary comment clusters | P1 | 🔓 OPEN (overlaps B05) |
| B03 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN |
| B04 | brief_ast name/colon / assignment target positions | P1 | 🔓 OPEN |
| B05 | Comment clusters merge across indent scopes | P1 | 🔓 OPEN (see D04) |
| B06 | `case` keyword via `rfind` heuristic | P1 | 🔓 OPEN |
| B07 | VENV recreate not transactional; rmtree on GUI thread | P1 | 🔓 OPEN (with D02) |
| B08 | Full-IDE smoke not a PR blocker; nightly ran on old SHA | P1 | 🔓 OPEN |
| C02 | Interpreter authenticity (probe) / mutable vs read-only | P1 | 🔓 OPEN |
| C03 | Recreate base=`sys.executable` changes Python version | P1 | 🔓 OPEN |
| C04 | Flow UI coupling test skips on any Exception | P1 | 🔓 OPEN |
| B09 | Schema not on all update paths | P2 | 🔓 OPEN |
| B10 | `Settings.flush` not atomic; atomic mode drift | P2 | 🔓 OPEN |
| B11 | Docs drift (README/TODO vs HEAD) | P2 | 🔓 OPEN |
| C05 | Empty UUID not persisted; `uuid1`→`uuid4` | P2 | 🔓 OPEN |

## Closed from prior audits

| ID | Topic | Status |
|----|-------|--------|
| A01 | Independent CI jobs + green | ✅ |
| A02–A03 | VENV mutate guards + async QProcess | ✅ |
| A04–A05 | brief CF defs; half-open spans / relative imports | ✅ |
| A07 | tokenize char columns + nested trailing | ✅ |
| A14 | profgraph drawPixmap | ✅ |

## Infrastructure (fact)

| Topic | State |
|-------|-------|
| **CI** | green on `8c60ad5c` (ruff / format / mypy / import-gates / tests 3.10–3.13 / wheel / smoke / security) |
| **Nightly** | ≥1 successful run (on old `179cb0a4`); need run on current HEAD |
| **Living Spec** | keep in sync with B\*/C\*/D\* |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
