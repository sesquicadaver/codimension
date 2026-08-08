# Codimension — Linear atomic roadmap

> **Language / Мова:** English | [Українська](ROADMAP.uk.md)

**Current tip (docs sync):** `master@c9da2526` (2026-08-08, after R138)  
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
| 8–9 Deps + local venv | DONE | T140/T141/R114 + DependencyManifest R120 |
| 10–13 Remote backends | DONE | ExecutionTarget R121–R125: local, Docker, SSH, Kubernetes MVPs |
| 14–20 Analysis | DONE | R130–R138: SymbolIndex, DependencyGraph, MetricProvider (+MI/Halstead/raw), OverlayLayer, git analytics, risk score |
| 21–24 Graph | PARTIAL → R142+ | R140–R141 (model, canvas bind, frame→node map) shipped; graph diff still OPEN |
| 25 Plugins | DONE | yapsy + bundled `cdmplugins/*` |
| 26 AI | MISSING → R151+ | SymbolIndex + metrics ready; needs CFG graph slice (R140.a) |
| 27–29 Extended overlays | MISSING → R160+ | Overlay **framework** R135 DONE; visual layers R160–R162 still OPEN |
| 30–38 Release/update | PARTIAL → R171+ | `ci-gate` + OIDC + branching policy (R170) exist; no channels/auto-update yet |

**Optimization applied:** solo-fork model — `master` + `feature/*` / `fix/*` + protected `ci-gate` (no `stable/develop` theatre). Auto-update apply/rollback stays deferred until read-only version check (R172–R173) works.

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

---

## Active queue (strict order — OPEN only)

| # | ID | Task | Acceptance | Size | Status |
|---|----|------|------------|------|--------|
| 1 | R142 | Graph diff between two CFGs / revisions | Diff API + tests on fixture pairs | M | OPEN |
| 2 | R143 | Function-local data-flow / taint MVP | Documented subset; tests for sources/sinks in one function | L | OPEN |
| 3 | R150 | Plugin capability / API version negotiation | Host rejects incompatible plugins cleanly; test | S | OPEN |
| 4 | R151 | AI context builder (headless): pack SymbolIndex + CFG slice for a symbol | Pure function + tests; no network | M | OPEN |
| 5 | R152 | AI UI actions behind feature flag (explain / suggest) | Flag off by default; smoke when flag on may mock backend | M | OPEN |
| 6 | R160 | Environment overlay visualization (env source / path badges on UI) | Uses R135; screenshot or widget test | M | OPEN |
| 7 | R161 | Dependency overlay (edge heat from DependencyGraph) | Uses R133+R135; test | M | OPEN |
| 8 | R162 | Deployment overlay hints (Dockerfile/compose detection) | Read-only hints; test on fixtures | S | OPEN |
| 9 | R171 | Release channel metadata in `cdmverspec` (`stable`/`beta`/`dev` label, still one version) | Field + docs; no multi-branch required | S | OPEN |
| 10 | R172 | In-app “check for updates” against GitHub Releases (read-only) | Shows newer tag if any; test with mocked HTTP | M | OPEN |
| 11 | R173 | Download + checksum verify update artifact | Writes to cache dir; verify fail closed; tests | M | OPEN |
| 12 | R174 | Feature flags module for experimental plugins/UI | Persistent flags; gate one existing experimental path; tests | S | OPEN |
| 13 | R175 | Safe-mode startup (disable plugins / overlays) | CLI or env `CDM_SAFE_MODE=1`; smoke | S | OPEN |

### Deferred (explicit)

| ID | Task | Why deferred |
|----|------|--------------|
| R180 | Auto-apply update + rollback / portable profiles | High risk; after R172–R173 proven |
| R181 | Full `develop`/`release` promotion pipeline | Overkill vs protected `master` + tags |
| R182 | MCP / remote IDE agent backend | Not on critical path; ExecutionTarget (R121–R125) already exists — schedule only on explicit product ask |

---

## Next autopilot pointer

**First OPEN:** `R142` — graph diff between two CFGs / revisions.

---

## Final architecture (target)

```text
Code → AST → CFG graph model → SymbolIndex → Metrics → Overlay → UI
ExecutionTarget: local | docker | ssh | k8s
Tooling: lint | test | profile | (AI via core context)
```
