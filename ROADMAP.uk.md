# Codimension — Об'єднаний дорожній план (Phase 0–38)

> **Мова / Language:** Українська | [English](ROADMAP.md)

> **Стан форку (2026-08):** Phase 0–1 + audit M1–M4 зелені (parsers/conformance, tooling/PAT, project scan, packaging CI 3.10–3.13). M5: `codimension.core` / `infrastructure` headless foundation (T080–T082, T085); T083–T084 MainWindow/GlobalData — відкриті. Деталі: [TODO_FIXME.md](TODO_FIXME.md), [doc/plugins/living-specification.md](doc/plugins/living-specification.md).

Повний англомовний текст фаз — у [ROADMAP.md](ROADMAP.md). Нижче — стислий огляд українською.

---

## Phase 0 — Baseline Stabilization

**Мета:** стабільна робота на Python 3.10+

- Виправити залежності (`pyproject`)
- Прибрати застарілі API
- Стабілізувати Qt-шар
- Забезпечити: відкриття проєкту, відкриття файлу, побудову CFG

**Критерій:** без падінь, детермінована поведінка.

---

## Phase 1 — Test Harness

**Мета:** зафіксувати поведінку

- CFG snapshot tests, parser tests, regression suite

**Критерій:** зміни CFG контрольовані.

---

## Phase 2–3 — Core / Modular Monolith

**Мета:** відокремити core від UI; модульна архітектура

```text
parse → AST
build_cfg → Graph
analyze → Metrics
```

Модулі: `core.*`, `app.*`, `ui.*`, `infra.*` — без циклічних залежностей, UI ізольовано.

---

## Phases 4–7 — Environment

Модель середовища аналізу, introspection, binding аналізаторів, кеш і invalidation. Джерело правди — project-bound environment.

---

## Phases 8–13 — Dependencies & Execution

Dependency discovery, backends: local venv, Docker, SSH, Kubernetes. Уніфікований `ExecutionTarget.run()`.

---

## Phases 14–20 — Core Analysis

Symbol index, dependency graph, metrics, overlays, advanced metrics, runtime profiling, Git analytics, composite risk model.

---

## Phases 21–24 — Graph Engine

Redesign graph engine, debugger graph mode, graph diff, data flow / taint analysis.

---

## Phases 25–26 — Plugins & AI

Plugin system, AI layer (після детермінованої системи).

---

## Phases 27–29 — Extended Overlays

Environment, dependency, deployment overlays.

---

## Phases 30–38 — Release / Branch / Update

Branching (`stable`, `develop`, `feature/*`, …), versioning (stable/beta/dev), CI/CD promotion, update channels, auto-update, deployment profiles, branch-aware UI, feature flags, rollback & recovery.

---

## Фінальна архітектура

```text
Code → AST → CFG → Symbol Index → Metrics → Overlay → UI

Execution Targets: venv | docker | ssh | k8s
Tooling: lint | test | profile
Plugins + AI (via core)
```

## Основні правила

1. Core ≠ UI
2. Execution через єдиний контракт
3. Environment = source of truth
4. Overlay = окремий шар
5. AI лише після детермінованої системи

## Результат

Модульна платформа аналізу коду з execution-aware, graph-based розумінням Python.
