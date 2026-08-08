# Codimension — Linear atomic roadmap

> **Language / Мова:** English | [Українська](ROADMAP.uk.md)

**Baseline:** `master@d8f2e786` (2026-08-06)  
**Living Spec:** [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md)  
**Autopilot:** first `OPEN` row below (after empty [TODO_FIXME.md](TODO_FIXME.md))

---

## How to use this queue

1. Work **strictly top-down**: first `OPEN` task only.
2. One task = **one PR** with tests + docs (ChangeLog, Living Spec, this file).
3. Mark `DONE` with merge SHA/PR when closed; never skip ahead without an explicit `BLOCKED` reason.
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
| DONE | Shipped on master |
| OPEN | Eligible for autopilot / next work |
| DEFERRED | Intentionally later; do not pull forward |

---

## Snapshot vs old Phase 0–38

| Old phases | Status now | Notes |
|------------|------------|-------|
| 0 Baseline | DONE | pyproject 3.10–3.13, Qt IDE, project/file, CFG |
| 1 Test harness | DONE | conformance snapshots + parser suite (~260 tests) |
| 2 Headless core | DONE | `core.syntax` / `core.flow` + `infrastructure/*` + T085 |
| 3 Modular monolith | DONE → R110+ | R100–R103: Qt-free utils piece, app façade, routing, boundary matrix |
| 4–7 Environment | DONE (R110–R114) | typed env, drivers, cache registry, optional auto-attach |
| 8–9 Deps + local venv | DONE (T140/T141/R114) | auto-on-open optional setting shipped |
| 10–13 Remote backends | DONE (R121–R125) | ExecutionTarget: local, Docker, SSH, Kubernetes MVPs |
| 14–20 Analysis | DONE (R130–R136) | SymbolIndex, DependencyGraph, MetricProvider (+ MI/Halstead/raw), OverlayLayer |
| 21–24 Graph | MISSING → R140+ | legacy `flowui` ≠ redesign |
| 25 Plugins | DONE | yapsy + bundled `cdmplugins/*` |
| 26 AI | MISSING → R151+ | after SymbolIndex |
| 27–29 Extended overlays | MISSING → R160+ | needs overlay framework R135 |
| 30–38 Release/update | PARTIAL → R170+ | `ci-gate` + OIDC exist; no channels/auto-update |

**Optimization applied:** dropped full `stable/develop` multi-branch theatre for a solo fork; keep `master` + `feature/*` + protected `ci-gate`. Auto-update apply/rollback is deferred until read-only version check works. K8s waits until Docker + SSH prove the contract.

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
| D-R113 | R113 | Analysis cache registry (brief/flow) + invalidate(project|file|env) |
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

---

## Active queue (strict order)

| # | ID | Task | Acceptance | Size | Status |
|---|----|------|------------|------|--------|
| 1 | R100 | Remove Qt import from `utils.importutils` (extract Qt-facing helpers to `ui/` or inject callable) | `scripts/check_core_import_graph.py` extended **or** dedicated gate: `utils.importutils` imports without `ui.qt`; existing import tests green | M | DONE |
| 2 | R101 | Add `codimension/app/` package: `ApplicationServices` façade (project load/unload hooks, no widgets) | Package importable headless; unit test constructs façade with fakes; Living Spec row | S | DONE |
| 3 | R102 | Route project open/unload through `app` façade (thin adapter from `GlobalData` / mainwindow) | Call graph shows UI → app → utils/project; no behavior change; regression tests | M | DONE |
| 4 | R103 | Document + enforce module boundary matrix (`core`/`infra`/`app`/`utils`/`ui`/`plugins`) in CI | Script fails on new illegal edges; matrix in Living Spec | M | DONE |
| 5 | R110 | Introduce immutable `AnalysisEnvironment` dataclass (python path, source kind, site-packages roots, project id) | Typed API + unit tests for project/session/auto/IDE sources matching today’s `describeAnalysisPythonSource` | M | DONE |
| 6 | R111 | Build `AnalysisEnvironment` from project via `venvbootstrap` (single constructor path) | All call sites that need “effective python” can use env object; tests cover precedence | M | DONE |
| 7 | R112 | Bind lint/tool drivers to `AnalysisEnvironment` (replace ad-hoc path fetches in `process_env` / drivers) | Drivers receive env; `tests/test_lint_drivers.py` + process_env tests updated | M | DONE |
| 8 | R113 | Analysis cache registry: register brief/flow caches; invalidate on env refresh + file change | API `invalidate(project|file|env)`; tests prove stale purge after interpreter change | M | DONE |
| 9 | R114 | Optional setting: auto-attach detected project venv on project open | Setting default off; when on, opens project sets session/project interpreter per policy; UI + test | S | DONE |
| 10 | R120 | `DependencyManifest`: formalize `collectInstallSources` → exportable requirements list / lock hint | Headless API + CLI/script or project action writes manifest; unit test | M | DONE |
| 11 | R121 | Define `ExecutionTarget` protocol (`run` / `debug` / `profile` / `which_python`) | Protocol in `core` or `app`; mypy-checked; fake target test | S | DONE |
| 12 | R122 | Adapt local process runner (`utils.run` / RunManager) to `ExecutionTarget` | Local runs go through protocol; existing argv/debug tests green | M | DONE |
| 13 | R123 | Docker `ExecutionTarget` MVP (image + mount workspace + run argv) | Integration test with docker-or-skip; docs; no GUI required for MVP | L | DONE |
| 14 | R124 | SSH `ExecutionTarget` MVP (remote python + sync or mount strategy documented) | Contract tests with mocked transport; docs for unverified platforms | L | DONE |
| 15 | R125 | Kubernetes `ExecutionTarget` MVP | Depends on R123+R124 lessons; job/pod run; docs | L | DONE |
| 16 | R130 | SymbolIndex schema (name, kind, file, half-open span, container) | Module + schema tests; Living Spec | S | DONE |
| 17 | R131 | Populate SymbolIndex from `brief_ast` for project files (async-friendly API) | Index build on sample project; accuracy tests vs known defs | M | DONE |
| 18 | R132 | Queries: `find_definitions` / `find_references` on SymbolIndex (bridge search provider) | Unit tests; occurrences provider can call index without behavior regress | M | DONE |
| 19 | R133 | Headless `DependencyGraph` from imports (reuse diagram logic without Qt) | Graph build test; optional export JSON | M | DONE |
| 20 | R134 | `MetricProvider` interface + radon CC adapter | Provider registry test; UI can keep current viewer | S | DONE |
| 21 | R135 | Overlay framework: `OverlayLayer` protocol + attach point on flow/editor (no heavy visuals yet) | Register empty overlay; test hook invoked on redraw/update | M | DONE |
| 22 | R136 | Advanced metrics pack (maintainability / raw/Halstead or documented subset) behind MetricProvider | At least 2 metrics beyond CC; tests with fixtures | M | DONE |
| 23 | R137 | Git analytics: churn / hotspot summary (git log based) | Headless report API + optional plugin panel; tests with temp repo | M | DONE |
| 24 | R138 | Composite risk score (lint + metrics + optional git) | Deterministic formula documented; unit tests; no AI | M | DONE |
| 25 | R140 | Headless CFG graph model separated from `flowui` canvas | `core`/`app` graph API from flow parse; canvas consumes model | L | OPEN |
| 26 | R141 | Debugger graph mode: map frames → CFG nodes | Offscreen/debugger test or documented manual + unit mapping | L | OPEN |
| 27 | R142 | Graph diff between two CFGs / revisions | Diff API + tests on fixture pairs | M | OPEN |
| 28 | R143 | Function-local data-flow / taint MVP | Documented subset; tests for sources/sinks in one function | L | OPEN |
| 29 | R150 | Plugin capability / API version negotiation | Host rejects incompatible plugins cleanly; test | S | OPEN |
| 30 | R151 | AI context builder (headless): pack SymbolIndex + CFG slice for a symbol | Pure function + tests; no network | M | OPEN |
| 31 | R152 | AI UI actions behind feature flag (explain / suggest) | Flag off by default; smoke when flag on may mock backend | M | OPEN |
| 32 | R160 | Environment overlay visualization (env source / path badges on UI) | Uses R135; screenshot or widget test | M | OPEN |
| 33 | R161 | Dependency overlay (edge heat from DependencyGraph) | Uses R133+R135; test | M | OPEN |
| 34 | R162 | Deployment overlay hints (Dockerfile/compose detection) | Read-only hints; test on fixtures | S | OPEN |
| 35 | R170 | Codify branching policy: `master` + `feature/*` / `fix/*` only; no direct push (doc + already protected `ci-gate`) | Doc in CONTRIBUTING + Living Spec; matches GitHub protection | S | OPEN |
| 36 | R171 | Release channel metadata in `cdmverspec` (`stable`/`beta`/`dev` label, still one version) | Field + docs; no multi-branch required | S | OPEN |
| 37 | R172 | In-app “check for updates” against GitHub Releases (read-only) | Shows newer tag if any; test with mocked HTTP | M | OPEN |
| 38 | R173 | Download + checksum verify update artifact | Writes to cache dir; verify fail closed; tests | M | OPEN |
| 39 | R174 | Feature flags module for experimental plugins/UI | Persistent flags; gate one existing experimental path; tests | S | OPEN |
| 40 | R175 | Safe-mode startup (disable plugins / overlays) | CLI or env `CDM_SAFE_MODE=1`; smoke | S | OPEN |

### Deferred (explicit)

| ID | Task | Why deferred |
|----|------|--------------|
| R180 | Auto-apply update + rollback / portable profiles | High risk; after R172–R173 proven |
| R181 | Full `develop`/`release` promotion pipeline | Overkill vs protected `master` + tags |
| R182 | MCP / remote IDE agent backend | Not in critical path; after ExecutionTarget |

---

## Next autopilot pointer

**First OPEN:** `R140` — Headless CFG graph model separated from `flowui`.

---

## Final architecture (target)

```text
Code → AST → CFG → SymbolIndex → Metrics → Overlay → UI
ExecutionTarget: local | docker | ssh | k8s
Tooling: lint | test | profile | (AI via core context)
```
