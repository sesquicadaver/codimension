# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-04 (повторний аудит master@f5196a67 + PR #19)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери (аудит 2026-08-04 @ f5196a67)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| B01 | VENV identity: `realpath(python)` плутає project venv з IDE | P0 | ✅ venv root vs `sys.prefix` |
| B02 | `.cdm3` uuid path traversal / без `uuid.UUID` | P0 | ✅ canonical UUID + `safe_user_project_dir` |
| B03 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN (was A09) |
| B04 | brief_ast name/colon positions | P1 | 🔓 OPEN (was A08) |
| B05 | Comment clusters merge across indent scopes | P1 | 🔓 OPEN |
| B06 | `case` keyword via `rfind` heuristic | P1 | 🔓 OPEN |
| B07 | VENV recreate не транзакційний; rmtree у GUI | P1 | 🔓 OPEN |
| B08 | Full-IDE smoke лише nightly (0 runs) / offscreen formal | P1 | 🔓 OPEN |
| B09 | Schema не на всіх update paths | P2 | 🔓 OPEN (was A10) |
| B10 | `Settings.flush` не atomic; atomic mode drift | P2 | 🔓 OPEN (was A11) |
| B11 | Docs drift (README/TODO vs commit) | P2 | 🔓 OPEN |

## Закриті з попередніх аудитів (підтверджено @ f5196a67)

| ID | Тема | Статус |
|----|------|--------|
| A01 | CI незалежні jobs + green | ✅ |
| A02–A03 | VENV mutate guards + async QProcess | ✅ (B01 — додатковий identity fix) |
| A04–A05 | brief CF defs; half-open spans / relative imports | ✅ |
| A07 | tokenize char columns + nested trailing | ✅ PR #19 |
| A14 | profgraph drawPixmap | ✅ |

## Інфраструктура (факт)

| Тема | Стан |
|------|------|
| **CI** | green на `f5196a67` (ruff / format / mypy / tests / wheel / smoke) |
| **Living Spec** | оновлювати разом із B01–B11 |

Жива матриця: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
