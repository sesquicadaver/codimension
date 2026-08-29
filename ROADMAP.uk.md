# Codimension — Лінійний атомарний roadmap

> **Мова / Language:** Українська | [English](ROADMAP.md)

**Поточний tip (синхронізація docs):** `master@c629dfd4` (2026-08-28, P1 A201–A210 закриті; черга R192+)  
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
| 8–9 Deps + local venv | DONE | T140/T141/R114/R176 + DependencyManifest R120 |
| 10–13 Remote backends | DONE | ExecutionTarget R121–R125 (local/Docker/SSH/K8s) |
| 14–20 Analysis | DONE | R130–R138 (індекс, графи імпортів, метрики, overlays framework, git analytics, risk) |
| 21–24 Graph | DONE → R150+ | R140–R143 (model, canvas, frames, diff, taint MVP) здано |
| 25 Plugins | DONE | yapsy + `cdmplugins/*` + R150 capability negotiation |
| 26 AI | DONE (MVP) | R151 context + R152 UI explain/suggest за flag (offline/mock; без LLM) |
| 27–29 Extended overlays | DONE | R135 + R160/R161/R162 (env, deps heat, deploy hints) |
| 30–38 Release/update | DONE + queued | R171–R175 здано; auto-apply = **R180** в активній черзі |

**Оптимізація:** модель соло-форку — `master` + `feature/*` / `fix/*` + protected `ci-gate`. Auto-apply = задача **R180** у лінійній черзі (після R172–R173).

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
| D-R173 | R173 | Verified download артефакту в cache (`utils.update_download`; fail closed) |
| D-R174 | R174 | Persistent feature flags (`core.feature_flags`); гейт AI UI (`ai_ui`) |
| D-R175 | R175 | Safe-mode старт (`--safe-mode` / `CDM_SAFE_MODE`); без плагінів і overlays |
| D-R176 | R176 | Політика проєктного venv (`projectVenvPolicy`); default auto_session + діагностика + клік Env: |
| D-R177 | R177 | Log → джерело: `path:line:` помилки імпортів + double-click у Log |
| D-R178 | R178 | Fallback host інструментів: IDE Python, якщо `-m` модуля немає в project venv |
| D-R179 | R179 | Встановлення відсутніх `-m` інструментів у project venv (діалог; IDE — opt-in) — PR #89 / `8c19d108` |
| D-R183 | R183 | SSH path containment (A201) — PR #106 |
| D-R184 | R184 | SSH host-key verification (A202) — PR #107 |
| D-R185 | R185 | SSH download hardening (A203) — PR #108 |
| D-R186 | R186 | SSH Run/Save async (A204) — PR #109 |
| D-R187 | R187 | ExecutionPlan vs Runner + K8s terminal (A205/A206) — PR #110 |
| D-R188 | R188 | Per-scope CFG + loop/finally (A207) — PR #110 |
| D-R189 | R189 | VENV create-in-final + backup/rollback (A208) — PR #111 |
| D-R190 | R190 | `.cdm3` external reload + UUID immutable (A209) — PR #112 |
| D-R191 | R191 | Plugin policy before import (A210) — PR #113 |

---

## Активна черга (суворий порядок — лише OPEN)

Лінійна **неблокуюча** черга: кожна задача — один PR; немає штучних `BLOCKED`/`DEFERRED` усередині хвилі. Порядок = пріоритет (безпека/стабільність → продукт → експерименти). Autopilot бере **перший** рядок зі статусом `OPEN`.

| # | ID | Задача | Acceptance | Size | Status |
|---|----|--------|------------|------|--------|
| 1 | R192 | AI HTTP: chunked/budgeted read + cancel + `base_url` trust allowlist (A220) | Немає unbounded `response.read()`; budget/cancel тести; чужий URL fail-closed | M | DONE |
| 2 | R193 | Settings: відхилення non-dict JSON; lazy singleton (A221) | Поганий JSON → safe defaults + log; Settings не ламає import | M | DONE |
| 3 | R194 | Risk/taint confidence; missing metrics ≠ штучно низький risk (A222) | Confidence/unknown у score; тести на відсутні метрики | M | DONE |
| 4 | R195 | Utils side-effect inventory + tighter boundary gate (A223.a) | Інвентар ефектів; gate ловить нові порушення матриці | M | DONE |
| 5 | R196 | Перший hotspot: інверсія залежності / винесення з `utils` (A223.b) | Один конкретний перенос + тести; Living Spec | M | DONE |
| 6 | R197 | Smoke: graceful shutdown замість `os._exit(0)`; wrapt/constraints (A224) | Нормальний teardown у smoke; constraints резолвляться без ручного wrapt hack | M | DONE |
| 7 | R198 | SSH remote Debug session MVP | Stop-at-first-line / continue через remote; contract Fake/інтеграція; docs | L | DONE ([#121](https://github.com/sesquicadaver/codimension/pull/121)) |
| 8 | R199 | SSH remote Profile MVP | Profile run remote + артефакт локально; cancel/timeout; docs | M | DONE |
| 9 | R180 | Auto-apply оновлення + rollback / portable profiles | Apply з verified cache; rollback; fail-closed; тести | L | DONE |
| 10 | R181 | Автоматизація promotion каналів (`dev`→`beta`→`stable` / tags) | Документований pipeline + скрипт/CI; без зайвого theatre | M | DONE |
| 11 | R182 | MCP / remote agent backend | MCP surface над headless core; auth fail-closed; smoke | L | DONE ([#126](https://github.com/sesquicadaver/codimension/pull/126)) |
| 12 | R200 | Polyglot: LanguageDescriptor + Registry + PythonService stub | `core/language.py` Protocol/Registry; `FLAG_LANGUAGE_SERVICES`; Python stub над існуючим SymbolIndex/brief/flow; без LSP; Living Spec | M | DONE ([#129](https://github.com/sesquicadaver/codimension/pull/129)) |
| 13 | R201 | Polyglot: DocumentSnapshot + LspPositionCodec | Лише Unicode offsets всередині; encoding на процес; versioned edits відхиляють stale | M | DONE ([#131](https://github.com/sesquicadaver/codimension/pull/131)) |
| 14 | R202 | Polyglot: LspProcess stdio JSON-RPC + spawn gate | Один процес на `(language_id, workspace_root, toolchain)`; cancel/backoff/shutdown; `LANGUAGE_SERVER_SPAWN` deny-by-default крім configured absolute binary | L | DONE ([#133](https://github.com/sesquicadaver/codimension/pull/133)) |
| 15 | R203 | Polyglot: Rust/C++ descriptors + SemanticProvider (LSP) | rust-analyzer / clangd; `compile_commands.json` → READY інакше DEGRADED (без претензії на повні diagnostics) | L | DONE |
| 16 | R204 | Polyglot: UI language controller (capability-driven) | Diagnostics / outline / hover / definition / references / format / rename-preview; без `if language == …` | L | OPEN |
| 17 | R205 | Polyglot: Tree-sitter StructuralGraph (Rust+C++) | StructuralGraph + `semantic_role`; **не** compiler CFG | L | OPEN |
| 18 | R206 | Polyglot: BindingIndex + PyO3 / pybind11 / CPython + `.pyi` | Лише evidence-backed FFI edges (без exact edge за однаковістю імен) | L | OPEN |
| 19 | R207 | Polyglot: DependencyEdgeKind + cross-language navigation | Узагальнені edges включно з FFI; навігація через мовну межу | M | OPEN |
| 20 | R208 | Polyglot: Cargo / CMake / Ninja / CTest TaskProviders | Лише explicit tasks (не при відкритті файла); не через clangd/rust-analyzer як build runners | M | OPEN |

---

## Вказівник autopilot

**Наступний OPEN:** **R204** (UI language controller, capability-driven).

Хвиля **R200–R208** = polyglot language layer (LSP + Tree-sitter + FFI + Tasks). Див. [polyglot-language-layer.md](doc/technology/polyglot-language-layer.md).

**Поза цією хвилею:** DAP/native debug; власні Rust/C++ parsers; Yapsy language plugins; копіювання Python CFG pipeline на інші мови.

Раніше відкладені R180–R182 і SSH Debug/Profile увійшли в активну чергу (2026-08-28) як атомарні задачі без окремого unlock.

### Поставлено поза R-чергою (вже в MVP / не дублювати)

| Область | Статус | Документація |
|---------|--------|--------------|
| SSH remote Open/Create + Browse… + Save upload + IDE Run | MVP | [ssh-remote-project.md](doc/technology/ssh-remote-project.md), [довідка](doc/user/ssh-remote-projects.md) |
| SSH remote Debug / Profile | Debug **R198** + Profile **R199** DONE | Ті самі docs |
| MCP stdio agent backend | **R182** DONE | [mcp-backend.md](doc/technology/mcp-backend.md) |

---

## Цільова архітектура

```text
Code → AST → CFG graph model → SymbolIndex → Metrics → Overlay → UI
ExecutionTarget: local | docker | ssh | k8s
Tooling: lint | test | profile | (AI via core context)
MCP / agent: **R182** (`mcp_backend`, stdio + ``CDM_MCP_TOKEN``)
Polyglot: LanguageServiceRegistry → LSP + Tree-sitter + FFI BindingIndex + Tasks (R200–R208)
```
