# Codimension — Лінійний атомарний roadmap

> **Мова / Language:** Українська | [English](ROADMAP.md)

**Поточний tip (синхронізація docs):** `master@c9da2526` (2026-08-08, після R138)  
**Історичний baseline черги:** `master@d8f2e786` (2026-08-06) — старт лінійного R100+  
**Living Spec:** [doc/plugins/living-specification.md](doc/plugins/living-specification.md)  
**Autopilot:** перший рядок `OPEN` в **Активній черзі** (після порожнього [TODO_FIXME.md](TODO_FIXME.md))

---

## Як користуватися чергою

1. Працювати **строго зверху вниз**: лише перша задача зі статусом `OPEN`.
2. Одна задача = **один PR** з тестами та документацією (ChangeLog, Living Spec, цей файл).
3. Після злиття позначати `DONE` (SHA/PR) і переносити рядок в **Архів**; не стрибати вперед без явного `BLOCKED`.
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
| DONE | Уже в master (лише в Архіві) |
| OPEN | Наступна робота / autopilot |
| DEFERRED | Свідомо пізніше |

---

## Зріз відносно старих Phase 0–38

| Старі фази | Зараз | Примітка |
|------------|-------|----------|
| 0 Baseline | DONE | pyproject 3.10–3.13, Qt IDE, проєкт/файл, CFG |
| 1 Test harness | DONE | conformance + parser (~348 `test_*` / 72 файли; лічильник пливе — дивись CI) |
| 2 Headless core | DONE | `core.syntax` / `core.flow` parse façade + `infrastructure/*` + T085 |
| 3 Modular monolith | DONE | R100–R103 |
| 4–7 Environment | DONE | R110–R114 |
| 8–9 Deps + local venv | DONE | T140/T141/R114 + DependencyManifest R120 |
| 10–13 Remote backends | DONE | ExecutionTarget R121–R125 (local/Docker/SSH/K8s) |
| 14–20 Analysis | DONE | R130–R138 (індекс, графи імпортів, метрики, overlays framework, git analytics, risk) |
| 21–24 Graph | DONE → R150+ | R140–R143 (model, canvas, frames, diff, taint MVP) здано |
| 25 Plugins | DONE | yapsy + `cdmplugins/*` + R150 capability negotiation |
| 26 AI | DONE (MVP) | R151 context + R152 UI explain/suggest за flag (offline/mock; без LLM) |
| 27–29 Extended overlays | DONE | R135 + R160/R161/R162 (env, deps heat, deploy hints) |
| 30–38 Release/update | PARTIAL → R173+ | Канал (R171) + read-only GitHub check (R172); download/verify ще OPEN |

**Оптимізація:** модель соло-форку — `master` + `feature/*` / `fix/*` + protected `ci-gate`. Auto-apply оновлень — після доведеного download+verify (R173).

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
| D-R111 | R111 | `buildAnalysisEnvironment(project)` — єдиний конструктор |
| D-R112 | R112 | Lint/tool drivers + process_env на AnalysisEnvironment |
| D-R113 | R113 | Registry кешів аналізу (brief/flow) + invalidate(project\|file\|env) |
| D-R114 | R114 | Опційне auto-attach проєктного venv при відкритті (session; Options) |
| D-R120 | R120 | `DependencyManifest` + export script; collectInstallSources через manifest |
| D-R121 | R121 | Протокол `ExecutionTarget` у `core.execution` + fake-тести |
| D-R122 | R122 | `LocalExecutionTarget` + `getCwdCmdEnv` через ExecutionTarget |
| D-R123 | R123 | `DockerExecutionTarget` MVP + docker-or-skip інтеграційний тест |
| D-R124 | R124 | `SSHExecutionTarget` + FakeSSHTransport; docs sync/платформи |
| D-R125 | R125 | `KubernetesExecutionTarget` + FakeK8sJobTransport; Job stub docs |
| D-R130 | R130 | схема `core.symbol_index` (SymbolRecord + half-open span) |
| D-R131 | R131 | Наповнення SymbolIndex з brief_ast (`utils.symbol_index_brief`) |
| D-R132 | R132 | `find_definitions` / `find_references` + міст occurrences |
| D-R133 | R133 | Headless `DependencyGraph` з імпортів (JSON/DOT export) |
| D-R134 | R134 | `MetricProvider` + registry + radon CC adapter |
| D-R135 | R135 | `OverlayLayer` + attach hosts flow/editor |
| D-R136 | R136 | Розширені метрики (MI + Halstead + raw LOC) |
| D-R137 | R137 | Git churn/hotspot analytics (`utils.git_analytics`) |
| D-R138 | R138 | Composite risk score `cdm-risk-v1` (`core.risk_score`) |
| D-R170 | R170 | Політика гілок: `master` + `feature/*` / `fix/*`; без прямого push (`ci-gate`) |
| D-R140.a | R140.a | Headless CFG graph model (`core.cfg`) з flow parse |
| D-R140.b | R140.b | `flowui.cfg_adapter` біндить `CfgGraph` у `layoutModule`; editor `getCfgGraph` |
| D-R141 | R141 | Debugger frames → CFG nodes (`core.cfg_frames`); анотація tooltip у stack |
| D-R142 | R142 | CFG graph diff (`core.cfg_diff`) через стабільні content keys |
| D-R143 | R143 | Function-local taint MVP (`core.taint`); задокументована підмножина |
| D-R150 | R150 | Plugin capability / API negotiation (`plugins.capabilities`) |
| D-R151 | R151 | AI context packer (`core.ai_context`): SymbolIndex + CFG slice |
| D-R152 | R152 | AI UI explain/suggest за `CDM_AI_UI` (default off; offline/mock backend) |
| D-R160 | R160 | Environment overlay: бейджі `env:source` + path на flow nav через R135 |
| D-R161 | R161 | Dependency overlay: edge heat з DependencyGraph через R135 |
| D-R162 | R162 | Deployment overlay: read-only Dockerfile/Compose hints через R135 |
| D-R171 | R171 | Метадані каналу в `cdmverspec` (`stable`/`beta`/`dev`) |
| D-R172 | R172 | In-app read-only перевірка GitHub Releases (`utils.update_check`) |

---

## Активна черга (суворий порядок — лише OPEN)

| # | ID | Задача | Acceptance | Size | Status |
|---|----|--------|------------|------|--------|
| 1 | R173 | Завантаження + перевірка checksum артефакту | Fail closed; тести | M | OPEN |
| 2 | R174 | Feature flags для experimental plugins/UI | Persistent flags + тест | S | OPEN |
| 3 | R175 | Safe-mode старт (`CDM_SAFE_MODE=1`, без плагінів/overlays) | Smoke | S | OPEN |

### Відкладено (явно)

| ID | Задача | Чому |
|----|--------|------|
| R180 | Auto-apply оновлення + rollback / portable profiles | Високий ризик; після R172–R173 |
| R181 | Повний pipeline `develop`→`release`→`stable` | Надлишково при protected `master` + tags |
| R182 | MCP / remote agent backend | Не на критичному шляху; ExecutionTarget (R121–R125) уже є — лише за явним запитом продукту |

---

## Вказівник autopilot

**Перший OPEN:** `R173` — завантаження + перевірка checksum артефакту.

---

## Цільова архітектура

```text
Code → AST → CFG graph model → SymbolIndex → Metrics → Overlay → UI
ExecutionTarget: local | docker | ssh | k8s
Tooling: lint | test | profile | (AI via core context)
```
