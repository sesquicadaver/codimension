# Codimension — Full Unified Roadmap (Phase 0–38)

---

# Phase 0 — Baseline Stabilization
**Goal:** Stable execution on Python 3.10+

### Tasks
- Fix dependencies (`pyproject`)
- Remove deprecated APIs
- Stabilize Qt layer
- Ensure:
  - open project
  - open file
  - build CFG

### Acceptance
- No crashes
- Deterministic behavior

---

# Phase 1 — Test Harness
**Goal:** Lock behavior

### Tasks
- CFG snapshot tests
- Parser tests
- Regression suite

### Acceptance
- CFG changes are controlled

---

# Phase 2 — Boundary Extraction
**Goal:** Separate core from UI

```python
parse → AST
build_cfg → Graph
analyze → Metrics

Acceptance

Core runs headless



---

Phase 3 — Modular Monolith

Goal: Controlled architecture

Modules

core.*
app.*
ui.*
infra.*

Acceptance

No cyclic deps

UI isolated



---

=== ENVIRONMENT ===

Phase 4 — Analysis Environment Model

Goal: Reliable context

Acceptance

Project-bound environment



---

Phase 5 — Environment Introspection

Goal: Real runtime data

Acceptance

Accurate import resolution



---

Phase 6 — Analyzer Binding

Goal: Consistency

Acceptance

Analysis depends on env



---

Phase 7 — Cache & Invalidation

Goal: No stale data


---

=== DEPENDENCIES & EXECUTION ===

Phase 8 — Dependency Discovery

Goal: Generate requirements


---

Phase 9 — Local venv Backend

Goal: Local isolation


---

Phase 10 — Docker Backend

Goal: Container isolation


---

Phase 11 — Remote (SSH)

Goal: Remote execution


---

Phase 12 — Unified Execution Target

ExecutionTarget.run()

Acceptance

Backend-agnostic execution



---

Phase 13 — Kubernetes Backend

Goal: Scale


---

=== CORE ANALYSIS ===

Phase 14 — Symbol Index & Dependency Graph


---

Phase 15 — Metric System


---

Phase 16 — Overlay System


---

Phase 17 — Advanced Metrics


---

Phase 18 — Runtime Profiling


---

Phase 19 — Git Analytics


---

Phase 20 — Composite Risk Model


---

=== GRAPH ENGINE ===

Phase 21 — Graph Engine Redesign


---

Phase 22 — Debugger Graph Mode


---

Phase 23 — Graph Diff


---

Phase 24 — Data Flow / Taint Analysis


---

=== PLUGINS ===

Phase 25 — Plugin System


---

=== AI ===

Phase 26 — AI Layer


---

=== OVERLAYS EXTENDED ===

Phase 27 — Environment Overlay


---

Phase 28 — Dependency Overlay


---

Phase 29 — Deployment Overlay


---

=== RELEASE / BRANCH / UPDATE ===

Phase 30 — Branching Model

Branches

stable

develop

feature/*

fix/*

release/*

hotfix/*


Rules

No direct commits to stable

stable updated via promotion only



---

Phase 31 — Versioning

Channels

stable

beta

dev



---

Phase 32 — CI/CD Promotion Pipeline

Flow

feature → develop → release → stable

Gates

tests

lint

CFG snapshot

packaging



---

Phase 33 — Update Channels

Channels

stable

beta

dev



---

Phase 34 — Auto-Update

Features

version check

download

verify

apply

rollback



---

Phase 35 — Deployment Profiles

Types

dev build

testing build

stable release

portable

container backend



---

Phase 36 — Branch-Aware UI

Features

version info

channel info

update status



---

Phase 37 — Stable vs Experimental

Features

feature flags

experimental plugins



---

Phase 38 — Rollback & Recovery

Features

previous version restore

safe mode



---

FINAL ARCHITECTURE

Code
 → AST
 → CFG
 → Symbol Index
 → Metrics
 → Overlay
 → UI

Execution Targets:
    venv
    docker
    ssh
    k8s

Tooling:
    lint
    test
    profile

Plugins
AI (via core)


---

CORE RULES

1. Core ≠ UI


2. Execution via unified contract


3. Environment = source of truth


4. Overlay = separate layer


5. AI only after deterministic system




---

FINAL RESULT

Modular code analysis platform with execution-aware, graph-based understanding of Python code