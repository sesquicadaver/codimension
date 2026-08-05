# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-05 (аудит master@a2c88921 / PR #28)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери (аудит @ a2c88921)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| B01 / B02 / C01 / D01 | VENV identity/UUID/destination/base combo | P0–P1 | ✅ |
| D03 | Redirected argv + `shell=False` | P1 | ✅ (redirected) |
| E01 / E02 | Custom-terminal launcher `${prog}` + Profile cProfile | P1 | ✅ |
| E04 / F07 | Stale cleanup symlink traversal у `/tmp` | P1 | ✅ lstat/O_NOFOLLOW + one-shot legacy `/tmp` |
| E04 (штатний unlink) | Launcher cleanup до execvp | P1 | ✅ |
| E05 | Profile timeout від shell `&` евристики; orphan `.done` | P1 | ✅ start deadline + marker cleanup |
| E06 | noexec execute-probe; обмеження shell-safe paths | P1 | ✅ exec probe + DQ-safe paths |
| D02 / B07 | VENV create/recreate без transaction/rollback | P1 | ✅ staging + commit |
| C02 / C03 | Interpreter probe; recreate=`sys.executable` | P1 | 🔓 OPEN |
| B03 | Project scan cancel/join/coalescing | P1 | 🔓 OPEN |
| B04 / B05 / B06 / D04 / D05 / D06 | Parser positions / CML / case / encoding / side comments | P1 | 🔓 OPEN |
| D07 / B08 / C04 | Production startup + plugin load; Flow UI skip | P1 | 🔓 OPEN |
| B11 | Docs drift (TODO/Living Spec/`doc/uk`, docs gate coverage) | P2 | 🔓 OPEN |
| B09 / B10 / C05 | Schema paths / atomic settings / UUID persist | P2 | 🔓 OPEN |
| D08 / E03 / G01 | Constraints / release verify / branch protection | P2 | 🔓 OPEN |

## Інфраструктура

| Тема | Стан |
|------|------|
| **CI** | перевіряти latest green Actions на HEAD (не static count у README) |
| **Docs gate** | `python scripts/check_docs.py` (partial: .md links; див. B11) |
| **Nightly full-IDE** | weekly, не PR-blocker |
| **Living Spec** | матриця модулів; без static SHA/test count |

Жива матриця: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
