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
| 9 | R180 | Auto-apply update + rollback / portable profiles | Apply from verified cache; rollback; fail-closed; tests | L | DONE ([#238](https://github.com/sesquicadaver/codimension/pull/238)) |
| 10 | R181 | Channel promotion automation (`dev`→`beta`→`stable` / tags) | Documented pipeline + script/CI; no theatre | M | DONE |
| 11 | R182 | MCP / remote agent backend | MCP surface over headless core; auth fail-closed; smoke | L | DONE ([#126](https://github.com/sesquicadaver/codimension/pull/126)) |
| 12 | R200 | Polyglot: LanguageDescriptor + Registry + PythonService stub | `core/language.py` Protocol/Registry; `FLAG_LANGUAGE_SERVICES`; Python stub over existing SymbolIndex/brief/flow; no LSP yet; Living Spec | M | DONE ([#129](https://github.com/sesquicadaver/codimension/pull/129)) |
| 13 | R201 | Polyglot: DocumentSnapshot + LspPositionCodec | Internal Unicode offsets only; per-process encoding; versioned edits reject stale | M | DONE ([#131](https://github.com/sesquicadaver/codimension/pull/131)) |
| 14 | R202 | Polyglot: LspProcess stdio JSON-RPC + spawn gate | One process per `(language_id, workspace_root, toolchain)`; cancel/backoff/shutdown; `LANGUAGE_SERVER_SPAWN` deny-by-default except configured absolute binary | L | DONE ([#133](https://github.com/sesquicadaver/codimension/pull/133)) |
| 15 | R203 | Polyglot: Rust/C++ descriptors + SemanticProvider (LSP) | rust-analyzer / clangd; `compile_commands.json` → READY else DEGRADED (no full-diagnostics claim) | L | DONE ([#135](https://github.com/sesquicadaver/codimension/pull/135)) |
| 16 | R204 | Polyglot: UI language controller (capability-driven) | Diagnostics / outline / hover / definition / references / format / rename-preview; no `if language == …` | L | DONE ([#137](https://github.com/sesquicadaver/codimension/pull/137)) |
| 17 | R205 | Polyglot: Tree-sitter StructuralGraph (Rust+C++) | StructuralGraph + `semantic_role` mapping; **not** compiler CFG | L | DONE ([#139](https://github.com/sesquicadaver/codimension/pull/139)) |
| 18 | R206 | Polyglot: BindingIndex + PyO3 / pybind11 / CPython + `.pyi` | Evidence-backed FFI edges only (no name-equality exact edges) | L | DONE ([#141](https://github.com/sesquicadaver/codimension/pull/141)) |
| 19 | R207 | Polyglot: DependencyEdgeKind + cross-language navigation | Generalized edges incl. FFI; navigation across language boundary | M | DONE ([#143](https://github.com/sesquicadaver/codimension/pull/143)) |
| 20 | R208 | Polyglot: Cargo / CMake / Ninja / CTest TaskProviders | Explicit tasks only (not on file open); not via clangd/rust-analyzer as build runners | M | DONE ([#145](https://github.com/sesquicadaver/codimension/pull/145)) |

### Hardening wave after 2026-09-05 audit (`codi-last.md` @ 340e97dc)

| # | ID | Task | Acceptance | Size | Status |
|---|-----|------|------------|------|--------|
| 21 | R209 | LSP document lifecycle: didChange / didClose / restart re-open | Versioned sync in `LspSemanticProvider`; `test_language_r209.py` | M | DONE ([#156](https://github.com/sesquicadaver/codimension/pull/156)) |
| 22 | R210 | LSP server→client requests | `workspace/configuration`, progress, dynamic registration; applyEdit refuse/preview | L | DONE ([#158](https://github.com/sesquicadaver/codimension/pull/158)) |
| 23 | R211 | SSH host-key pin before auth | Verify presented key before authentication | M | DONE ([#159](https://github.com/sesquicadaver/codimension/pull/159)) |
| 24 | R212 | SSH Debug bind/containment | Bind `127.0.0.1`; remote→local containment; cancellable polling | M | DONE ([#160](https://github.com/sesquicadaver/codimension/pull/160)) |
| 25 | R213 | Binding validation vs project cache | Only bindings matching current project cache + saved profile | M | DONE ([#161](https://github.com/sesquicadaver/codimension/pull/161)) |
| 26 | R214 | MCP workspace policy | Immutable allowed root + resource budgets | M | DONE ([#162](https://github.com/sesquicadaver/codimension/pull/162)) |
| 27 | R215 | Updater provenance hardening | Trusted provenance, HTTPS/host policy, streaming limits, version probe | M | DONE ([#164](https://github.com/sesquicadaver/codimension/pull/164)) |
| 28 | R216 | CFG loop-else / match paths | Correct loop-else and no-match paths | M | DONE ([#166](https://github.com/sesquicadaver/codimension/pull/166)) |
| 29 | R217 | FFI: no EXACT without registration chain | Do not claim `EXACT` without full registration evidence | M | DONE ([#168](https://github.com/sesquicadaver/codimension/pull/168)) |
| 30 | R218 | AI docstring: versioned target + post-patch validate | Identity on versioned snapshot; validate after apply | M | DONE ([#170](https://github.com/sesquicadaver/codimension/pull/170)) |
| 31 | R219 | Project reload: immutable UUID + diff/rebuild | Single pipeline; UUID immutable | M | DONE ([#172](https://github.com/sesquicadaver/codimension/pull/172)) |
| 32 | R220 | Plugin policy before import | Fail-closed policy before importing plugin code | M | DONE ([#174](https://github.com/sesquicadaver/codimension/pull/174)) |

### Hardening wave after 2026-09-06 re-audit (`codi-last.md` @ 8824ff3c)

| # | ID | Task | Acceptance | Size | Status |
|---|-----|------|------------|------|--------|
| 33 | R221 | SSH binding: cache path == `remote_cache_dir(profile, remote_root)` | Reject binding when `local_root` ≠ expected cache for `remote_root` | M | DONE ([#177](https://github.com/sesquicadaver/codimension/pull/177)) |
| 34 | R222 | Updater: validate every redirect hop + final URL | Custom `HTTPRedirectHandler`; `geturl()` re-checked via trust policy | M | DONE ([#179](https://github.com/sesquicadaver/codimension/pull/179)) |
| 35 | R223 | MCP: budget-aware workspace walker | Depth/file/byte limits during traversal; chunked reads; stop on exceed | M | DONE ([#181](https://github.com/sesquicadaver/codimension/pull/181)) |
| 36 | R224 | LSP DocumentStore for foreign URI spans | Cross-file definition/refs/rename use real ranges (no `SourceSpan(0,0)`) | L | DONE ([#183](https://github.com/sesquicadaver/codimension/pull/183)) |
| 37 | R225 | Plugin manifest policy fail-closed | Third-party: required `.cdmp` Codimension block; unknown/invalid → deny (no legacy import) | M | DONE ([#185](https://github.com/sesquicadaver/codimension/pull/185)) |
| 38 | R226 | FFI EXACT via structural parse | Tree-sitter/LSP evidence for registration chain; else BRIDGE/INFERRED | L | DONE ([#187](https://github.com/sesquicadaver/codimension/pull/187)) |
| 39 | R227 | Taint: `posonlyargs` + branch lattice union | Clone env per branch; may-taint join; cover positional-only params | M | DONE ([#189](https://github.com/sesquicadaver/codimension/pull/189)) |
| 40 | R228 | Blank UUID after load | Reject empty disk UUID or atomically restore loaded UUID to `.cdm3` | S | DONE ([#191](https://github.com/sesquicadaver/codimension/pull/191)) |
| 41 | R229 | Polyglot capabilities match providers | Advertise only implemented diagnostics/completion/tokens APIs | M | DONE ([#193](https://github.com/sesquicadaver/codimension/pull/193)) |
| 42 | R230 | Wire LanguageServiceManager into IDE lifecycle | Compose into GlobalData/MainWindow workspace open/close | L | DONE ([#194](https://github.com/sesquicadaver/codimension/pull/194)) |
| 43 | R231 | AI structured findings + global budgets | Finding model + total token/cost budget (beyond per-file truncate) | L | DONE ([#195](https://github.com/sesquicadaver/codimension/pull/195)) |

### Hardening wave after re-audit 2026-09-07 (`codi-last.md` @ 45e33f6 / HEAD 4ff0207b)

| # | ID | Task | Acceptance | Size | Status |
|---|-----|------|------------|------|--------|
| 44 | R232 | Plugin re-enable pre-import gate | Every `loadPlugins()` (incl. `materializePlugin`) re-checks manifest + file identity | M | DONE ([#196](https://github.com/sesquicadaver/codimension/pull/196)) |
| 45 | R233 | LSP generation-safe lifecycle | Atomic restart+initialize; no requests before handshake; clear `_opened` on generation bump | M | DONE ([#197](https://github.com/sesquicadaver/codimension/pull/197)) |
| 46 | R234 | LSP pending synchronization | `_pending_lock`; `(generation, id)` keys; timeout/shutdown/old-reader race tests | L | DONE ([#198](https://github.com/sesquicadaver/codimension/pull/198)) |
| 47 | R235 | Workspace DocumentStore | Single editor-backed store; versioned edits; deny unresolved/`(0,0)` apply; bounded loader | L | DONE ([#199](https://github.com/sesquicadaver/codimension/pull/199)) |
| 48 | R236 | Project lifecycle façade | create/load/switch/unload only via `ApplicationServices` (fix `createNew` bypass) | M | DONE ([#201](https://github.com/sesquicadaver/codimension/pull/201)) |
| 49 | R237 | AI redirect trust | Every redirect hop + final URL pass provider scheme/host policy | M | DONE ([#203](https://github.com/sesquicadaver/codimension/pull/203)) |
| 50 | R238 | MCP fd-safe bounded traversal | Entry/dir budgets; `scandir`; `O_NOFOLLOW`; deterministic walk | L | DONE ([#205](https://github.com/sesquicadaver/codimension/pull/205)) |
| 51 | R239 | Taint CFG worklist | Forward per-node lattice; no whole-list re-exec; exception/no-match/loop-else | L | DONE ([#207](https://github.com/sesquicadaver/codimension/pull/207)) |
| 52 | R240 | FFI edge-specific structural proof | `EXACT` only with full registration-chain identity (module/binder/export/native) | L | DONE ([#209](https://github.com/sesquicadaver/codimension/pull/209)) |
| 53 | R241 | AI hard budgets + cancellation | Provider output caps; post-check; deadline; cancel; evidence/path validation | L | DONE ([#211](https://github.com/sesquicadaver/codimension/pull/211)) |
| 54 | R242 | Polyglot editor integration | Buffer open/change/close snapshots; capability-driven IDE actions | L | DONE ([#213](https://github.com/sesquicadaver/codimension/pull/213)) |
| 55 | R243 | CI/release/docs hardening | Coverage; Bandit gate; LSP race tests; SHA-pinned Actions; docs sync | M | DONE ([#215](https://github.com/sesquicadaver/codimension/pull/215)) |
| 56 | R244 | LSP transport lease + generation isolation | Pending registration + write atomic; stale requests/notifications never hit new process | L | DONE ([#217](https://github.com/sesquicadaver/codimension/pull/217)) |
| 57 | R245 | Editor-owned document versioning | No version regression; Save As close(old)→open(new) | M | DONE ([#219](https://github.com/sesquicadaver/codimension/pull/219)) |
| 58 | R246 | Foreign URI boundary | Reject UNRESOLVED opens; canonical URI; fd-rooted loader | L | DONE ([#220](https://github.com/sesquicadaver/codimension/pull/220)) |
| 59 | R247 | MCP pre-materialization budgets | max_entries before full collection/sort | M | DONE ([#221](https://github.com/sesquicadaver/codimension/pull/221)) |
| 60 | R248 | SSH atomic replace | posix_rename or backup/swap/rollback; Fake matches SFTP | M | DONE ([#222](https://github.com/sesquicadaver/codimension/pull/222)) |
| 61 | R249 | AI cost-aware provider cap | Provider max_tokens ≤ token/cost remainder | M | DONE ([#223](https://github.com/sesquicadaver/codimension/pull/223)) |
| 62 | R250 | pybind11 CST-exact proof | EXACT only from real .def() call_expression | L | DONE ([#225](https://github.com/sesquicadaver/codimension/pull/225)) |
| 63 | R251 | Residual correctness | AI finding source-bind; plugin package identity; transactional switch; terminal taint; CI floor | L | DONE ([#227](https://github.com/sesquicadaver/codimension/pull/227)) |
| 64 | R252 | LSP initialized transport lease | No application write until handshake complete for that generation | L | DONE ([#230](https://github.com/sesquicadaver/codimension/pull/230)) |
| 65 | R253 | Generation-atomic document request | didOpen/didChange + semantic request on one lease; restart re-syncs | L | DONE ([#231](https://github.com/sesquicadaver/codimension/pull/231)) |
| 66 | R254 | Fail-closed plugin package identity | Oversized/unreadable member always deny; bounded entries/depth/bytes | L | DONE ([#232](https://github.com/sesquicadaver/codimension/pull/232)) |
| 67 | R255 | Durable SSH replace transaction | Unique temps, serialized dest, phase recovery, crash/fault tests | L | DONE ([#233](https://github.com/sesquicadaver/codimension/pull/233)) |
| 68 | R256 | LSP/URI residual hardening | Pending rollback on write fail; NUL reject; no O_NOFOLLOW bypass | M | DONE ([#234](https://github.com/sesquicadaver/codimension/pull/234)) |
| 69 | R257 | Transactional project switch | Pre-validate + rollback previous project on any failure | L | DONE ([#235](https://github.com/sesquicadaver/codimension/pull/235)) |
| 70 | R258 | Taint terminal-edge lattice | Separate normal/return/break/continue/raise; join only normal paths | L | DONE ([#236](https://github.com/sesquicadaver/codimension/pull/236)) |
| 71 | R259 | AI validation hardening | Finite numeric config; evidence in declared line range | M | DONE ([#238](https://github.com/sesquicadaver/codimension/pull/238)) |
| 72 | R260 | Reliability test wave | Barriers, SSH crash phases, oversized plugin, lifecycle rollback; coverage climb | L | DONE ([#240](https://github.com/sesquicadaver/codimension/pull/240)) |
| 73 | R261 | SSH replace state machine hardening | No crash loses sole valid copy; atomic bound marker; fault tests per op | L | DONE ([#243](https://github.com/sesquicadaver/codimension/pull/243)) |
| 74 | R262 | Generation-pinned LSP notifications | didOpen/didChange/request stay on one generation; restart starts with didOpen | L | DONE ([#244](https://github.com/sesquicadaver/codimension/pull/244)) |
| 75 | R263 | Canonical DocumentStore identity | URI aliases share state; OPEN_BUFFER never replaced by DISK | L | DONE ([#245](https://github.com/sesquicadaver/codimension/pull/245)) |
| 76 | R264 | Plugin fd-relative identity walk | Symlink files/dirs fail-closed; all executable package content in identity | L | DONE |
| 77 | R265 | Full project lifecycle transaction | Rollback covers detach/unload/load/attach; clean partial load without prior project | L | OPEN |
| 78 | R266 | LSP worker and payload hardening | Immutable transport lease for workers; reader death invalidates; strict range decode | L | OPEN |
| 79 | R267 | Multi-exit taint environments | ExitKind→env map; finally per edge; nested loop exit stack | L | OPEN |
| 80 | R268 | Runtime invariants and CI precision | Strict explicit AI config; reliability coverage precision; TODO sync | M | OPEN |

---

## Next autopilot pointer

**Next OPEN:** **R265** — Full project lifecycle transaction.

Wave **R200–R208** = polyglot language layer (LSP + Tree-sitter + FFI + Tasks). See [polyglot-language-layer.md](doc/technology/polyglot-language-layer.md).

Wave **R209–R220** = hardening from audit `codi-last.md` @ 340e97dc (DONE).

Wave **R221–R231** = hardening from re-audit `codi-last.md` @ 8824ff3c (DONE).

Wave **R232–R243** = hardening from re-audit `codi-last.md` @ 45e33f6 (DONE).

Wave **R244–R251** = hardening from re-audit `codi-last.md` @ 645d655 (master@cf241873; DONE).

Wave **R252–R260** = hardening from re-audit `codi-last.md` @ master@eaa3dfee (DONE; residuals → R261–R268).

Wave **R261–R268** = hardening from re-audit `codi-last.md` @ master@f44c8dc4 (recommended queue §1–8).


**Out of this wave:** DAP/native debug; own Rust/C++ parsers; Yapsy language plugins; copying the Python CFG pipeline to other languages; HMAC-signed bindings (optional stretch).

Formerly deferred R180–R182 and SSH Debug/Profile entered the active queue (2026-08-28) as atomic tasks without a separate unlock gate.

### Shipped outside the R-queue (MVP — do not duplicate)

| Area | Status | Docs |
|------|--------|------|
| SSH remote project Open/Create + Browse… + Save upload + IDE Run | MVP | [ssh-remote-project.md](doc/technology/ssh-remote-project.md), [user guide](doc/user/ssh-remote-projects.md) |
| SSH remote Debug / Profile | Debug **R198** + Profile **R199** DONE | Same docs |
| MCP stdio agent backend | **R182** + **R214** DONE | [mcp-backend.md](doc/technology/mcp-backend.md) |

---

## Final architecture (target)

```text
Code → AST → CFG graph model → SymbolIndex → Metrics → Overlay → UI
ExecutionTarget: local | docker | ssh | k8s
Tooling: lint | test | profile | (AI via core context)
MCP / agent: **R182** + **R214** (`mcp_backend`, stdio + token + workspace policy)
Polyglot: LanguageServiceRegistry → LSP + Tree-sitter + FFI BindingIndex + Tasks (R200–R208); hardening R209–R231 DONE; R232–R243 re-audit wave
```
