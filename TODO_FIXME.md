# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-05 (аудит master@628c78d7 / PR #22)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери (аудит 2026-08-05 @ 628c78d7)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| B01 / B02 / C01 | VENV identity, UUID containment, create destination | P0 | ✅ |
| D01 | Base interpreter combo ігнорує Browse/`setEditText` | P1 | ✅ |
| D03 | Run/debug/profile args через `shell=True` ламають argv | P1 | ✅ argv + `shell=False` (redirected); custom terminal quoted |
| D02 | Initial VENV create без rollback | P1 | 🔓 OPEN |
| D04 | CML губиться всередині ordinary comment clusters | P1 | 🔓 OPEN (з B05) |
| D05 | Encoding cookie на 2-му рядку може бути пропущений | P1 | 🔓 OPEN |
| D06 | Side comments багаторядкових headers не прив’язуються | P1 | 🔓 OPEN |
| D07 | Full-IDE smoke ≠ production entrypoint + plugin load | P1 | 🔓 OPEN (з B08) |
| B03 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN |
| B04 | brief_ast name/colon / assignment positions | P1 | 🔓 OPEN |
| B05 | Comment clusters merge across indent scopes | P1 | 🔓 OPEN |
| B06 | `case` keyword via `rfind` heuristic | P1 | 🔓 OPEN |
| B07 | VENV recreate не транзакційний; rmtree у GUI | P1 | 🔓 OPEN (з D02) |
| B08 | Full-IDE smoke не PR-blocker / старий nightly SHA | P1 | 🔓 OPEN |
| C02 | Interpreter authenticity (probe) / mutable vs read-only | P1 | 🔓 OPEN |
| C03 | Recreate base=`sys.executable` змінює версію Python | P1 | 🔓 OPEN |
| C04 | Flow UI coupling test з `pytest.skip` на Exception | P1 | 🔓 OPEN |
| B09 | Schema не на всіх update paths | P2 | 🔓 OPEN |
| B10 | `Settings.flush` не atomic; atomic mode drift | P2 | 🔓 OPEN |
| B11 | Docs drift (README/TODO vs HEAD) | P2 | 🔓 OPEN |
| C05 | Порожній UUID не персиститься; `uuid1`→`uuid4` | P2 | 🔓 OPEN |
| D08 | Немає відтворюваних dependency constraints/lock | P2 | 🔓 OPEN |

## Закриті з попередніх аудитів

| ID | Тема | Статус |
|----|------|--------|
| A01–A05 / A07 / A14 | CI, VENV guards, parsers, drawPixmap | ✅ |

## Інфраструктура (факт)

| Тема | Стан |
|------|------|
| **CI** | green на `628c78d7` (matrix 3.10–3.13 + ruff/mypy/wheel/smoke) |
| **Nightly** | ≥1 успішний run на старому SHA; потрібен прогін актуального HEAD |
| **Living Spec** | оновлювати разом із B\*/C\*/D\* |

Жива матриця: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
