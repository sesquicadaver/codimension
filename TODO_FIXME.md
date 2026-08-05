# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-05 (аудит master@8c60ad5c / PR #21)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери (аудит 2026-08-05 @ 8c60ad5c)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| B01 | VENV identity: `realpath(python)` плутає project venv з IDE | P0 | ✅ |
| B02 | `.cdm3` uuid path traversal / без `uuid.UUID` | P0 | ✅ |
| C01 | Create VENV без destination guard | P0 | ✅ `validateVenvDestination` sync+QProcess |
| D01 | Base interpreter combo: Browse/`setEditText` ігнорується (`currentData`) | P1 | ✅ `selectedBaseInterpreter` |
| D02 | Initial VENV create без rollback (partial dir блокує retry) | P1 | 🔓 OPEN |
| D03 | Run/debug/profile args через `shell=True` ламають межі argv | P1 | 🔓 OPEN |
| D04 | CML губиться всередині ordinary comment clusters | P1 | 🔓 OPEN (перетинається з B05) |
| B03 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN |
| B04 | brief_ast name/colon / assignment target positions | P1 | 🔓 OPEN |
| B05 | Comment clusters merge across indent scopes | P1 | 🔓 OPEN (див. D04) |
| B06 | `case` keyword via `rfind` heuristic | P1 | 🔓 OPEN |
| B07 | VENV recreate не транзакційний; rmtree у GUI | P1 | 🔓 OPEN (з D02) |
| B08 | Full-IDE smoke не PR-blocker; nightly був на старому SHA | P1 | 🔓 OPEN |
| C02 | Interpreter authenticity (probe) / mutable vs read-only | P1 | 🔓 OPEN |
| C03 | Recreate base=`sys.executable` змінює версію Python | P1 | 🔓 OPEN |
| C04 | Flow UI coupling test з `pytest.skip` на Exception | P1 | 🔓 OPEN |
| B09 | Schema не на всіх update paths | P2 | 🔓 OPEN |
| B10 | `Settings.flush` не atomic; atomic mode drift | P2 | 🔓 OPEN |
| B11 | Docs drift (README/TODO vs HEAD) | P2 | 🔓 OPEN |
| C05 | Порожній UUID не персиститься; `uuid1`→`uuid4` | P2 | 🔓 OPEN |

## Закриті з попередніх аудитів

| ID | Тема | Статус |
|----|------|--------|
| A01 | CI незалежні jobs + green | ✅ |
| A02–A03 | VENV mutate guards + async QProcess | ✅ |
| A04–A05 | brief CF defs; half-open spans / relative imports | ✅ |
| A07 | tokenize char columns + nested trailing | ✅ |
| A14 | profgraph drawPixmap | ✅ |

## Інфраструктура (факт)

| Тема | Стан |
|------|------|
| **CI** | green на `8c60ad5c` (ruff / format / mypy / import-gates / tests 3.10–3.13 / wheel / smoke / security) |
| **Nightly** | був ≥1 успішний run (на старому `179cb0a4`); потрібен прогін актуального HEAD |
| **Living Spec** | оновлювати разом із B\*/C\*/D\* |

Жива матриця: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
