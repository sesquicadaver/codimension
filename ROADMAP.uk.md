# Codimension — Лінійний атомарний roadmap

> **Мова / Language:** Українська | [English](ROADMAP.md)

**Базовий зріз:** `master@d8f2e786` (2026-08-06)  
**Living Spec:** [doc/plugins/living-specification.md](doc/plugins/living-specification.md)  
**Autopilot:** перший рядок `OPEN` нижче (після порожнього [TODO_FIXME.md](TODO_FIXME.md))

---

## Як користуватися чергою

1. Працювати **строго зверху вниз**: лише перша задача зі статусом `OPEN`.
2. Одна задача = **один PR** з тестами та документацією (ChangeLog, Living Spec, цей файл).
3. Після злиття позначати `DONE` (SHA/PR); не стрибати вперед без явного `BLOCKED`.
4. Якщо задача виявилась завеликою — **розщепити** на `Rxxx.a` / `Rxxx.b`, зберігаючи порядок.
5. Правила: Core ≠ UI; execution через один контракт; environment = source of truth; overlays окремим шаром; AI лише після детермінованого індексу/CFG.

### Розмір

| Size | Значення |
|------|----------|
| S | ≤1 день / один модуль |
| M | 2–4 дні / кілька модулів |
| L | багатоденна / архітектурна |

### Статус

| Status | Значення |
|--------|----------|
| DONE | Уже в master |
| OPEN | Наступна робота / autopilot |
| DEFERRED | Свідомо пізніше |

---

## Зріз відносно старих Phase 0–38

| Старі фази | Зараз | Примітка |
|------------|-------|----------|
| 0 Baseline | DONE | pyproject 3.10–3.13, Qt IDE, проєкт/файл, CFG |
| 1 Test harness | DONE | golden CFG + conformance (~260 тестів) |
| 2 Headless core | DONE | `core.syntax` / `core.flow` + `infrastructure/*` + T085 |
| 3 Modular monolith | DONE → R110+ | R100–R103: Qt-free utils, app фасад, routing, матриця меж |
| 4–7 Environment | PARTIAL → R111+ | є `AnalysisEnvironment` (R110); далі конструктор/drivers/cache |
| 8–9 Deps + local venv | DONE (T140/T141) | auto-on-open опційно → R114 |
| 10–13 Remote backends | MISSING → R121+ | немає `ExecutionTarget` / Docker / SSH / K8s |
| 14–20 Analysis | PARTIAL → R130+ | діаграми/метрики/profiling є; немає SymbolIndex/overlays/risk |
| 21–24 Graph | MISSING → R140+ | legacy `flowui` ≠ redesign |
| 25 Plugins | DONE | yapsy + `cdmplugins/*` |
| 26 AI | MISSING → R151+ | після SymbolIndex |
| 27–29 Extended overlays | MISSING → R160+ | потрібен фреймворк R135 |
| 30–38 Release/update | PARTIAL → R170+ | є `ci-gate` + OIDC; немає channels/auto-update |

**Оптимізація:** для форку з `master` + `feature/*` не нав’язуємо повний `stable/develop` цирк. Auto-apply оновлень — після read-only version check. K8s — після Docker + SSH.

---

## Архів — DONE (не ставити знову в чергу)

| ID | Було | Здано |
|----|------|-------|
| D0 | Phase 0 | Пакети 3.10–3.13, Qt shell, проєкт/файл, CFG |
| D1 | Phase 1 | CFG snapshots + brief/flow conformance |
| D2 | Phase 2 | Headless parse + infrastructure |
| D3a | Phase 3 (частково) | T085: `core`/`infrastructure` без Qt |
| D9 | Phase 9 / T140–T141 | VENV UI, транзакції, Env:, refresh |
| D25 | Phase 25 | Plugin host + інструментальні плагіни |
| D-audit | TODO_FIXME P0–P2 | B01–G01 закриті |
| D-R100 | R100 | `utils.importutils` без Qt; progress через callback; T085 покриває модуль |
| D-R101 | R101 | `codimension.app.ApplicationServices` + headless тести; packaging |
| D-R102 | R102 | UI/startup load+unload через `GlobalData.appServices` |
| D-R103 | R103 | Матриця меж шарів + CI gate (`check_module_boundaries.py`) |
| D-R110 | R110 | Immutable `AnalysisEnvironment` + тести паритету |

---

## Активна черга (суворий порядок)

| # | ID | Задача | Acceptance | Size | Status |
|---|----|--------|------------|------|--------|
| 1 | R100 | Прибрати імпорт Qt з `utils.importutils` (винести в `ui/` або DI) | Gate / тест: модуль без `ui.qt`; існуючі import-тести зелені | M | DONE |
| 2 | R101 | Пакет `codimension/app/`: фасад `ApplicationServices` (load/unload без віджетів) | Headless імпорт + unit з фейками; рядок у Living Spec | S | DONE |
| 3 | R102 | Відкриття/unload проєкту через `app` (тонкий адаптер з GlobalData/mainwindow) | UI → app → utils/project; без регресій | M | DONE |
| 4 | R103 | Матриця меж модулів (`core`/`infra`/`app`/`utils`/`ui`/`plugins`) у CI | Скрипт падає на нові заборонені ребра | M | DONE |
| 5 | R110 | Immutable `AnalysisEnvironment` (шлях python, source kind, site-packages, id проєкту) | Typed API + тести паритету з `describeAnalysisPythonSource` | M | DONE |
| 6 | R111 | Збирати `AnalysisEnvironment` з проєкту через `venvbootstrap` | Єдиний конструктор; тести precedence | M | OPEN |
| 7 | R112 | Прив’язати lint/tool drivers до `AnalysisEnvironment` | Drivers отримують env; оновлені тести | M | OPEN |
| 8 | R113 | Registry кешів аналізу + invalidate на env refresh / зміну файлу | API invalidate; тест на stale після зміни інтерпретатора | M | OPEN |
| 9 | R114 | Опція: auto-attach проєктного venv при відкритті | Default off; UI + тест | S | OPEN |
| 10 | R120 | `DependencyManifest` з `collectInstallSources` → експорт requirements | Headless API + тест | M | OPEN |
| 11 | R121 | Протокол `ExecutionTarget` (`run` / `debug` / `profile` / `which_python`) | Protocol + fake target тест | S | OPEN |
| 12 | R122 | Локальний runner (`utils.run` / RunManager) через `ExecutionTarget` | Існуючі argv/debug тести зелені | M | OPEN |
| 13 | R123 | Docker `ExecutionTarget` MVP | docker-or-skip інтеграційний тест; docs | L | OPEN |
| 14 | R124 | SSH `ExecutionTarget` MVP | Мокований транспорт; docs | L | OPEN |
| 15 | R125 | Kubernetes `ExecutionTarget` MVP | Після R123+R124; docs | L | OPEN |
| 16 | R130 | Схема SymbolIndex (name, kind, file, half-open span, container) | Модуль + тести; Living Spec | S | OPEN |
| 17 | R131 | Наповнення SymbolIndex з `brief_ast` по файлах проєкту | Тести точності на фікстурах | M | OPEN |
| 18 | R132 | Запити `find_definitions` / `find_references` (+ міст до search) | Unit + без регресії occurrences | M | OPEN |
| 19 | R133 | Headless `DependencyGraph` з імпортів (без Qt) | Тест побудови; опційний JSON export | M | OPEN |
| 20 | R134 | Інтерфейс `MetricProvider` + адаптер radon CC | Registry тест | S | OPEN |
| 21 | R135 | Overlay framework: `OverlayLayer` + точка підключення (без важкої графіки) | Реєстрація порожнього overlay; тест хука | M | OPEN |
| 22 | R136 | Розширені метрики (≥2 понад CC) через MetricProvider | Фікстури + тести | M | OPEN |
| 23 | R137 | Git analytics: churn / hotspot (git log) | Headless API + тест на temp repo | M | OPEN |
| 24 | R138 | Composite risk score (lint + metrics ± git) | Документована формула; unit; без AI | M | OPEN |
| 25 | R140 | Headless CFG graph model окремо від canvas `flowui` | API з flow parse; canvas споживає модель | L | OPEN |
| 26 | R141 | Debugger graph mode: кадри → вузли CFG | Mapping unit / offscreen | L | OPEN |
| 27 | R142 | Graph diff двох CFG / ревізій | Diff API + фікстури | M | OPEN |
| 28 | R143 | Function-local data-flow / taint MVP | Задокументований підмножина + тести | L | OPEN |
| 29 | R150 | Версіонування capabilities плагінів | Несумісний плагін відхиляється; тест | S | OPEN |
| 30 | R151 | AI context builder (headless): SymbolIndex + зріз CFG | Чиста функція + тести; без мережі | M | OPEN |
| 31 | R152 | AI UI-дії за feature flag | Flag default off | M | OPEN |
| 32 | R160 | Environment overlay (бейджі джерела env) | На базі R135 | M | OPEN |
| 33 | R161 | Dependency overlay (тепло ребер) | R133+R135 | M | OPEN |
| 34 | R162 | Deployment overlay (Dockerfile/compose hints) | Read-only; фікстури | S | OPEN |
| 35 | R170 | Політика гілок: лише `master` + `feature/*`/`fix/*` (doc + `ci-gate`) | CONTRIBUTING + Living Spec | S | OPEN |
| 36 | R171 | Метадані каналу в `cdmverspec` (`stable`/`beta`/`dev`) | Поле + docs | S | OPEN |
| 37 | R172 | In-app «перевірити оновлення» (GitHub Releases, read-only) | Мокований HTTP тест | M | OPEN |
| 38 | R173 | Завантаження + перевірка checksum артефакту | Fail closed; тести | M | OPEN |
| 39 | R174 | Feature flags для experimental plugins/UI | Persistent flags + тест | S | OPEN |
| 40 | R175 | Safe-mode старт (`CDM_SAFE_MODE=1`, без плагінів/overlays) | Smoke | S | OPEN |

### Відкладено (явно)

| ID | Задача | Чому |
|----|--------|------|
| R180 | Auto-apply оновлення + rollback / portable profiles | Високий ризик; після R172–R173 |
| R181 | Повний pipeline `develop`→`release`→`stable` | Надлишково при protected `master` + tags |
| R182 | MCP / remote agent backend | Після ExecutionTarget |

---

## Вказівник autopilot

**Перший OPEN:** `R111` — збирати `AnalysisEnvironment` з проєкту через `venvbootstrap`.

---

## Цільова архітектура

```text
Code → AST → CFG → SymbolIndex → Metrics → Overlay → UI
ExecutionTarget: local | docker | ssh | k8s
Tooling: lint | test | profile | (AI via core context)
```
