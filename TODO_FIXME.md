# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-03 (повторний аудит master@179cb0a4 + hotfix P0 у робочому дереві)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери (повторний аудит 2026-08-03)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| A01 | Master CI червоний (Ruff I001) + послідовні lint gates | P0 | 🔧 hotfix: I001 + незалежні jobs |
| A02 | VENV: silent configured→`sys.executable`; pip/recreate IDE env | P0 | 🔧 hotfix: `SOURCE_INVALID` + mutate guards |
| A03 | VENV sync `subprocess.run` блокує GUI | P0 | ✅ `ui/venvprocess.py` (QProcess + progress/cancel) |
| A04 | brief_ast: module-level defs у control-flow | P0 | 🔧 hotfix: `_iter_suite_statements` на module |
| A05 | flow_ast: `ImportFrom.level`; half-open spans; case header | P0 | ✅ half-open `_body_from_abs_range` + root `end=len` |
| A06 | Документація завищувала DONE/CI-green | P0 | 🔧 цей файл / Living Spec |
| A07 | Comment binder: tokenize char vs AST byte columns; nested trailing | P1 | 🔓 OPEN |
| A08 | brief_ast: name/colon positions | P1 | 🔓 OPEN |
| A09 | Project scan thread cancel/join lifecycle | P1 | 🔓 OPEN |
| A10 | `updateProperties` / `onProjectFileUpdated` без schema validate | P2 | 🔓 OPEN |
| A11 | `Settings.flush` не atomic | P2 | 🔓 OPEN |
| A12 | T130 nightly: IMPLEMENTED / NOT YET VERIFIED (0 runs) | P2 | 🔓 OPEN |
| A14 | `profgraph.Function.paint`: `drawPixmap(QRectF, pixmap)` invalid on PyQt5 | P0 | 🔧 fixed: 3-arg with sourceRect |

## Завершений базис 2026-08 (T001–T141)

Інфраструктура remediation (parsers foundation, PAT, packaging, MainWindow MRO, VENV UI T140/T141) **реалізована в коді**, але **не означає production-ready** і не означає «усі gates зелені» без верифікації CI.

| Блок | Код | Верифікація |
|------|-----|-------------|
| Parsers / conformance (T001–T029) | ✅ | частково; див. A04–A08 |
| Tooling / credentials / scan (T030–T052) | ✅ | scan lifecycle A09 |
| Packaging / CI / core (T060–T085) | ✅ | CI layout A01 |
| Debugger e2e (T100–T130) | ✅ код | T130 nightly A12 |
| Project VENV + Env: (T140–T141) | ✅ UI | safety A02 ✅; async A03 ✅ |

## Заглушки `pass` (потребують перевірки)

- **flowui/everything.py** — демо-файл для flow UI, ігнорується ruff
- **runmanager.py, mainstatusbar.py** — `pass` у except/empty handlers
- **variablesbrowser.py, notused.py, brief_ast.py** — `pass` у обробниках
- **vcsannotateviewer.py, classesviewer.py** — `pass` у методах
- **profgraph.py, importsdgm.py, asyncfile_cdm_dbg.py** — `pass` у обробниках
- **wpointviewer.py, editorsmanager.py** — `pass` у обробниках
- **resultprovideriface.py** — абстрактний інтерфейс
- **profiletest.py** — тестовий файл профілювання

## Інфраструктура (факт)

| Тема | Стан |
|------|------|
| **Unit-тести** | `pytest tests/` — **181** passed / 2 skipped (локально після A03/A05) |
| **CI** | незалежні jobs: ruff / ruff-format / mypy / import-gates / test / wheel / smoke; `permissions: contents: read` |
| **Living Spec** | має відображати OPEN пункти аудиту, не лише `[x] CI проходить` |

Жива матриця: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
