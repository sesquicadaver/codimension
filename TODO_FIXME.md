# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-08 (черга синхронізована з master@c9da2526; аудит P0–P2 закритий раніше @ d8f2e786 / PR #40)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери

Аудиторні P0–P2 з TODO закриті. Подальша робота — лінійна черга атомарних задач у [ROADMAP.uk.md](ROADMAP.uk.md) (перший OPEN: **R171**).

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
| C02 / C03 | Interpreter probe; recreate=`sys.executable` | P1 | ✅ probe + version-matched base |
| B03 | Project scan cancel/join/coalescing | P1 | ✅ interrupt + coalesce + no GUI sync fallback |
| B04 | brief keyword/name/colon + target/alias positions | P1 | ✅ `TokenIndex` + identifier spans |
| D05 | Encoding cookie на 2-му рядку після false «coding» | P1 | ✅ scan both lines until real cookie |
| B05 / D04 | CML clustering + indentation scopes | P1 | ✅ split on indent / CML head / cml+ |
| B06 | `case` keyword через `rfind` | P1 | ✅ `TokenIndex.find_name_before` |
| D06 | Side comments багаторядкових headers | P1 | ✅ header line span |
| D07 / B08 | Production startup + plugin load | P1 | ✅ bundled paths + full `imp` + smoke gate |
| C04 | Flow UI import → `pytest.skip` | P1 | ✅ fail on import; only skip missing PyQt5 / TryStar |
| B11 | Docs drift (TODO/Living Spec/`doc/uk`, docs gate coverage) | P2 | ✅ parity + expanded `check_docs` |
| B09 / B10 / C05 | Schema paths / atomic settings / UUID persist | P2 | ✅ validate all paths; atomic flush; uuid4 + immediate save |
| D08 / E03 / G01 | Constraints / release verify / branch protection | P2 | ✅ constraints snapshot; release verify+OIDC; `ci-gate` + master protection |

## Інфраструктура

| Тема | Стан |
|------|------|
| **CI** | перевіряти latest green Actions на HEAD (не static count у README) |
| **Docs gate** | `python scripts/check_docs.py` (links/images/dirs/anchors/ref/HTML; UA↔EN; TODO↔Living Spec; CI matrix) |
| **Nightly full-IDE** | weekly, не PR-blocker |
| **Living Spec** | матриця модулів; без static SHA/test count |

Жива матриця: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
