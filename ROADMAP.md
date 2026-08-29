# Codimension — Linear atomic roadmap

> **Language / Мова:** English | [Українська](ROADMAP.uk.md)

**Current tip (docs sync):** `master@c629dfd4` (2026-08-28, P1 A201–A210 closed; queue R192+)  
**Queue freeze baseline (historical):** `master@d8f2e786` (2026-08-06) — start of the linear R100+ rebuild  
**Living Spec:** [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md)  
**Autopilot:** first `OPEN` row in **Active queue** (after empty [TODO_FIXME.md](TODO_FIXME.md))

---

## How to use this queue

1. Work **strictly top-down**: first `OPEN` task only.
2. One task = **one PR** with tests + docs (ChangeLog, Living Spec, this file).
3. Mark `DONE` with merge SHA/PR when closed; move the row to **Archive**; never skip ahead without an explicit `BLOCKED` reason.
4. If a task is still too large in practice — **split** it into `Rxxx.a` / `Rxxx.b` and keep order.
5. Core rules (unchanged): Core ≠ UI; execution via one contract; environment is source of truth; overlays are a separate layer; AI only after deterministic index/CFG.

### Size legend

| Size | Meaning |
|------|---------|
| S | ≤1 day / single module |
| M | 2–4 days / few modules |
| L | multi-day / architectural |

### Status legend

| Status | Meaning |
|--------|---------|
| DONE | Shipped on master (listed in Archive only) |
| OPEN | Eligible for autopilot / next work |
| DEFERRED | Intentionally later; do not pull forward |

---

## Snapshot vs old Phase 0–38

| Old phases | Status now | Notes |
|------------|------------|-------|
| 0 Baseline | DONE | pyproject 3.10–3.13, Qt IDE, project/file, CFG |
| 1 Test harness | DONE | conformance + parser suite (~348 `test_*` functions / 72 files; count drifts — use CI) |
| 2 Headless core | DONE | `core.syntax` / `core.flow` parse façade + `infrastructure/*` + T085 |
| 3 Modular monolith | DONE | R100–R103: Qt-free utils piece, app façade, routing, boundary matrix |
| 4–7 Environment | DONE | R110–R114: typed env, drivers, cache registry, optional auto-attach |
| 8–9 Deps + local venv | DONE | T140/T141/R114/R176 + DependencyManifest R120 |
| 10–13 Remote backends | DONE | ExecutionTarget R121–R125: local, Docker, SSH, Kubernetes MVPs |
| 14–20 Analysis | DONE | R130–R138: SymbolIndex, DependencyGraph, MetricProvider (+MI/Halstead/raw), OverlayLayer, git analytics, risk score |
| 21–24 Graph | DONE → R150+ | R140–R143 (model, canvas, frames, diff, taint MVP) shipped |
| 25 Plugins | DONE | yapsy + `cdmplugins/*` + R150 capability negotiation |
| 26 AI | DONE (MVP) | R151 context + R152 flag-gated UI explain/suggest (offline/mock; no LLM) |
| 27–29 Extended overlays | DONE | R135 framework + R160 env + R161 deps heat + R162 deploy hints |
| 30–38 Release/update | DONE + queued | R171–R175 shipped; auto-apply = **R180** in active queue |

**Optimization applied:** solo-fork model — `master` + `feature/*` / `fix/*` + protected `ci-gate` (no `stable/develop` theatre). Auto-update apply/rollback is **R180** in the linear queue (after R172–R173).

---

## Archive — DONE (do not re-queue)

| ID | Was | Delivered |
|----|-----|-----------|
| D0 | Phase 0 | Python 3.10–3.13 packaging, Qt shell, open project/file, CFG path |
| D1 | Phase 1 | CFG golden snapshots + brief/flow conformance |
| D2 | Phase 2 | Headless parse APIs + infrastructure facades |
| D3a | Phase 3 (partial) | T085: `core`/`infrastructure` Qt-free |
| D9 | Phase 9 / T140–T141 | Project VENV UI, transactional create/recreate, Env: status, refresh |
| D25 | Phase 25 | Plugin host + Ruff/Mypy/Pytest/Coverage/Bandit/pip-audit/TODO/Git |
| D-audit | TODO_FIXME P0–P2 | B01–G01 closed (startup, parsers, persistence, docs, constraints, release, branch protection) |
| D-R100 | R100 | `utils.importutils` Qt-free; progress via callback; T085 gate covers the module |
| D-R101 | R101 | `codimension.app.ApplicationServices` façade + headless tests; packaging |
| D-R102 | R102 | UI/startup load+unload via `GlobalData.appServices` |
| D-R103 | R103 | Named-layer boundary matrix + CI gate (`check_module_boundaries.py`) |
| D-R110 | R110 | Immutable `AnalysisEnvironment` dataclass + parity tests |
| D-R111 | R111 | `buildAnalysisEnvironment(project)` single constructor; effective python via env |
| D-R112 | R112 | Lint/tool drivers + process_env bound to AnalysisEnvironment |
| D-R113 | R113 | Analysis cache registry (brief/flow) + invalidate(project\|file\|env) |
| D-R114 | R114 | Optional auto-attach project venv on open (session overlay; Options toggle) |
| D-R120 | R120 | `DependencyManifest` + export script; collectInstallSources via manifest |
| D-R121 | R121 | `ExecutionTarget` protocol in `core.execution` + fake target tests |
| D-R122 | R122 | `LocalExecutionTarget` + `getCwdCmdEnv` via ExecutionTarget |
| D-R123 | R123 | `DockerExecutionTarget` MVP + docker-or-skip integration test |
| D-R124 | R124 | `SSHExecutionTarget` + FakeSSHTransport contract tests; sync docs |
| D-R125 | R125 | `KubernetesExecutionTarget` + FakeK8sJobTransport; Job stub docs |
| D-R130 | R130 | `core.symbol_index` schema (SymbolRecord + half-open span) |
| D-R131 | R131 | Populate SymbolIndex from brief_ast (`utils.symbol_index_brief`) |
| D-R132 | R132 | `find_definitions` / `find_references` + occurrences index bridge |
| D-R133 | R133 | Headless `DependencyGraph` from imports (JSON/DOT export) |
| D-R134 | R134 | `MetricProvider` + registry + radon CC adapter |
| D-R135 | R135 | `OverlayLayer` + flow/editor attach hosts |
| D-R136 | R136 | Advanced metrics pack (MI + Halstead + raw LOC) |
| D-R137 | R137 | Git churn/hotspot analytics (`utils.git_analytics`) |
| D-R138 | R138 | Composite risk score `cdm-risk-v1` (`core.risk_score`) |
| D-R170 | R170 | Branching policy documented: `master` + `feature/*` / `fix/*`; no direct push (`ci-gate`) |
| D-R140.a | R140.a | Headless CFG graph model (`core.cfg`) from flow parse |
| D-R140.b | R140.b | `flowui.cfg_adapter` binds `CfgGraph` in `layoutModule`; editor `getCfgGraph` |
| D-R141 | R141 | Debugger frames → CFG nodes (`core.cfg_frames`); stack tooltip annotation |
| D-R142 | R142 | CFG graph diff (`core.cfg_diff`) via stable content keys |
| D-R143 | R143 | Function-local taint MVP (`core.taint`); documented subset |
| D-R150 | R150 | Plugin capability / API negotiation (`plugins.capabilities`) |
| D-R151 | R151 | AI context packer (`core.ai_context`): SymbolIndex + CFG slice |
| D-R152 | R152 | AI UI explain/suggest behind `CDM_AI_UI` (default off; offline/mock backend) |
| D-R160 | R160 | Environment overlay: `env:source` + path badges on flow nav via R135 |
| D-R161 | R161 | Dependency overlay: edge heat from DependencyGraph via R135 |
| D-R162 | R162 | Deployment overlay: read-only Dockerfile/Compose hints via R135 |
| D-R171 | R171 | Release channel metadata in `cdmverspec` (`stable`/`beta`/`dev`) |
| D-R172 | R172 | In-app read-only GitHub Releases update check (`utils.update_check`) |
| D-R173 | R173 | Verified update artifact download to cache (`utils.update_download`; fail closed) |
| D-R174 | R174 | Persistent feature flags (`core.feature_flags`); gates AI UI (`ai_ui`) |
| D-R175 | R175 | Safe-mode startup (`--safe-mode` / `CDM_SAFE_MODE`); plugins + overlays off |
| D-R176 | R176 | Project venv policy (`projectVenvPolicy`); default auto_session + diagnostics + Env: click |
| D-R177 | R177 | Log click-to-source: `path:line:` import errors + LogViewer double-click |
| D-R178 | R178 | Tool host fallback: IDE Python when `-m` tool missing in project venv |
| D-R179 | R179 | Install missing `-m` tools into project venv (dialog; IDE host opt-in) — PR #89 / `8c19d108` |
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

## Active queue (strict order — OPEN only)

Linear **non-blocking** queue: one task = one PR; no artificial `BLOCKED`/`DEFERRED` inside the wave. Order = priority (safety/stability → product → experiments). Autopilot takes the **first** `OPEN` row.

| # | ID | Task | Acceptance | Size | Status |
|---|----|------|------------|------|--------|
| 1 | R192 | AI HTTP: chunked/budgeted read + cancel + `base_url` trust allowlist (A220) | No unbounded `response.read()`; budget/cancel tests; untrusted URL fail-closed | M | DONE |
| 2 | R193 | Settings: reject non-dict JSON; lazy singleton (A221) | Bad JSON → safe defaults + log; Settings import-safe | M | DONE |
| 3 | R194 | Risk/taint confidence; missing metrics ≠ understated risk (A222) | Confidence/unknown in score; tests for missing metrics | M | DONE |
| 4 | R195 | Utils side-effect inventory + tighter boundary gate (A223.a) | Inventory; gate catches new matrix violations | M | DONE |
| 5 | R196 | First hotspot: invert dependency / extract from `utils` (A223.b) | One concrete move + tests; Living Spec | M | DONE |
| 6 | R197 | Smoke: graceful shutdown instead of `os._exit(0)`; wrapt/constraints (A224) | Normal teardown in smoke; constraints resolve without manual wrapt hack | M | DONE |
| 7 | R198 | SSH remote Debug session MVP | Stop-at-first-line / continue remote; Fake/integration contracts; docs | L | DONE ([#121](https://github.com/sesquicadaver/codimension/pull/121)) |
| 8 | R199 | SSH remote Profile MVP | Remote profile + local artifact; cancel/timeout; docs | M | DONE |
| 9 | R180 | Auto-apply update + rollback / portable profiles | Apply from verified cache; rollback; fail-closed; tests | L | DONE |
| 10 | R181 | Channel promotion automation (`dev`→`beta`→`stable` / tags) | Documented pipeline + script/CI; no theatre | M | DONE |
| 11 | R182 | MCP / remote agent backend | MCP surface over headless core; auth fail-closed; smoke | L | DONE ([#126](https://github.com/sesquicadaver/codimension/pull/126)) |
| 12 | R200 | Polyglot: LanguageDescriptor + Registry + PythonService stub | `core/language.py` Protocol/Registry; `FLAG_LANGUAGE_SERVICES`; Python stub over existing SymbolIndex/brief/flow; no LSP yet; Living Spec | M | DONE ([#129](https://github.com/sesquicadaver/codimension/pull/129)) |
| 13 | R201 | Polyglot: DocumentSnapshot + LspPositionCodec | Internal Unicode offsets only; per-process encoding; versioned edits reject stale | M | DONE ([#131](https://github.com/sesquicadaver/codimension/pull/131)) |
| 14 | R202 | Polyglot: LspProcess stdio JSON-RPC + spawn gate | One process per `(language_id, workspace_root, toolchain)`; cancel/backoff/shutdown; `LANGUAGE_SERVER_SPAWN` deny-by-default except configured absolute binary | L | DONE ([#133](https://github.com/sesquicadaver/codimension/pull/133)) |
| 15 | R203 | Polyglot: Rust/C++ descriptors + SemanticProvider (LSP) | rust-analyzer / clangd; `compile_commands.json` → READY else DEGRADED (no full-diagnostics claim) | L | DONE |
| 16 | R204 | Polyglot: UI language controller (capability-driven) | Diagnostics / outline / hover / definition / references / format / rename-preview; no `if language == …` | L | OPEN |
| 17 | R205 | Polyglot: Tree-sitter StructuralGraph (Rust+C++) | StructuralGraph + `semantic_role` mapping; **not** compiler CFG | L | OPEN |
| 18 | R206 | Polyglot: BindingIndex + PyO3 / pybind11 / CPython + `.pyi` | Evidence-backed FFI edges only (no name-equality exact edges) | L | OPEN |
| 19 | R207 | Polyglot: DependencyEdgeKind + cross-language navigation | Generalized edges incl. FFI; navigation across language boundary | M | OPEN |
| 20 | R208 | Polyglot: Cargo / CMake / Ninja / CTest TaskProviders | Explicit tasks only (not on file open); not via clangd/rust-analyzer as build runners | M | OPEN |

---

## Next autopilot pointer

**Next OPEN:** **R204** (UI language controller, capability-driven).

Wave **R200–R208** = polyglot language layer (LSP + Tree-sitter + FFI + Tasks). See [polyglot-language-layer.md](doc/technology/polyglot-language-layer.md).

**Out of this wave:** DAP/native debug; own Rust/C++ parsers; Yapsy language plugins; copying the Python CFG pipeline to other languages.

Formerly deferred R180–R182 and SSH Debug/Profile entered the active queue (2026-08-28) as atomic tasks without a separate unlock gate.

### Shipped outside the R-queue (MVP — do not duplicate)

| Area | Status | Docs |
|------|--------|------|
| SSH remote project Open/Create + Browse… + Save upload + IDE Run | MVP | [ssh-remote-project.md](doc/technology/ssh-remote-project.md), [user guide](doc/user/ssh-remote-projects.md) |
| SSH remote Debug / Profile | Debug **R198** + Profile **R199** DONE | Same docs |
| MCP stdio agent backend | **R182** DONE | [mcp-backend.md](doc/technology/mcp-backend.md) |

---

## Final architecture (target)

```text
Code → AST → CFG graph model → SymbolIndex → Metrics → Overlay → UI
ExecutionTarget: local | docker | ssh | k8s
Tooling: lint | test | profile | (AI via core context)
MCP / agent: **R182** (`mcp_backend`, stdio + ``CDM_MCP_TOKEN``)
Polyglot: LanguageServiceRegistry → LSP + Tree-sitter + FFI BindingIndex + Tasks (R200–R208)
```
