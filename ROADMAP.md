# Codimension — Unified Roadmap

---

## Phase 0 — Baseline Stabilization
**Goal:** Stable execution on Python 3.10+

### Tasks
- Fix dependencies (`pyproject`)
- Remove deprecated APIs
- Stabilize Qt layer
- Ensure basic workflows:
  - open project
  - open file
  - build CFG

### Artifacts
- Reproducible environment
- CI (lint + run)

### Acceptance
- No crashes in basic scenarios
- Deterministic behavior

---

## Phase 1 — Test Harness
**Goal:** Lock current behavior

### Tasks
- CFG snapshot tests
- Parser tests
- Regression suite

### Artifacts
- `tests/core/*`

### Acceptance
- CFG changes are controlled and intentional

---

## Phase 2 — Boundary Extraction
**Goal:** Separate core from UI

### Contracts
```python
parse → AST
build_cfg → Graph
analyze → Metrics

Tasks

Extract parser / CFG / model

Remove Qt dependency from core


Acceptance

Core runs independently (CLI/headless)



---

Phase 3 — Modular Monolith

Goal: Controlled architecture

Modules

core.*
app.*
ui.*
infra.*

Acceptance

No cyclic dependencies

UI does not affect core



---

=== ENVIRONMENT & EXECUTION ===

Phase 4 — Analysis Environment Model

Goal: Reliable analysis context

Entity

AnalysisEnvironment

Tasks

Interpreter binding

Environment registry

Project-level binding


Acceptance

Each project has active environment



---

Phase 5 — Environment Introspection

Goal: Real runtime context

Tasks

Collect sys.path

Detect site-packages

Python version

Platform info


Acceptance

Import resolution uses real environment data



---

Phase 6 — Analyzer Binding

Goal: Consistent analysis

Tasks

Bind:

lint

type checking

test runners

dead code analysis



Acceptance

Changing environment changes analysis results



---

Phase 7 — Environment Cache & Invalidation

Goal: Consistency

Tasks

Environment fingerprint

Cache invalidation

Reindex on change


Acceptance

No stale analysis data



---

=== DEPENDENCIES & PROVISIONING ===

Phase 8 — Dependency Discovery

Goal: Auto-generate requirements

Tasks

Import scanning

Package resolution

Requirements synthesis


Artifacts

requirements.txt

pyproject draft


Acceptance

Correct dependency detection



---

Phase 9 — Local venv Backend

Goal: Local isolation

Tasks

Create/reuse venv

Install dependencies

Bind to project


Acceptance

Fully functional local environment



---

Phase 10 — Docker Backend

Goal: Runtime isolation

Tasks

Generate Dockerfile

Build/run container

Collect artifacts


Acceptance

Analysis runs inside container



---

Phase 11 — Remote (SSH)

Goal: Remote project support

Tasks

Remote filesystem

Remote execution

Synchronization


Acceptance

Full analysis over SSH



---

Phase 12 — Unified Execution Target

Goal: Single execution contract

ExecutionTarget.run()

Types

venv

docker

ssh

k8s


Acceptance

Plugins are backend-agnostic



---

Phase 13 — Kubernetes Backend

Goal: Scalability

Tasks

Job orchestration

Artifact retrieval


Acceptance

Heavy analysis runs in cluster



---

=== CORE ANALYSIS ===

Phase 14 — Symbol Index & Dependency Graph

Goal: Analysis foundation

Tasks

Symbol table

References

Import graph

Call graph


Acceptance

Fast navigation and indexing



---

Phase 15 — Metric System

Goal: Unified metrics

MetricProvider

Metrics

LOC

Cyclomatic complexity

Nesting depth


Acceptance

Metrics independent from UI



---

Phase 16 — Overlay System

Goal: Visual diagnostics

Overlays

Size

Complexity

Nesting


Acceptance

Fast switching

Clear legend



---

Phase 17 — Advanced Metrics

Goal: Practical insights

Integrations

Coverage

Ruff

Mypy / Pyright


Acceptance

Accurate issue visualization



---

Phase 18 — Runtime Profiling

Goal: Performance analysis

Metrics

Self time

Total time

Call count


Acceptance

Heatmap on CFG



---

Phase 19 — Git Analytics

Goal: Risk detection

Metrics

Churn

Change frequency


Acceptance

Highlight unstable code zones



---

Phase 20 — Composite Risk Model

Goal: Integrated risk scoring

risk = f(metrics)

Acceptance

Explainable risk score



---

=== GRAPH ENGINE ===

Phase 21 — Graph Engine Redesign

Goal: Scalability

Tasks

Incremental CFG updates

Caching

Lazy rendering


Acceptance

Large files without lag



---

Phase 22 — Debugger Graph Mode

Goal: Runtime visualization

Acceptance

Execution path highlighted



---

Phase 23 — Graph Diff

Goal: Structural change analysis

Acceptance

CFG diff between revisions



---

Phase 24 — Data Flow / Taint Analysis

Goal: Deep analysis

Acceptance

Source → sink tracking



---

=== PLUGINS ===

Phase 25 — Plugin System

Goal: Extensibility

Plugin hooks

Acceptance

External plugins without core changes



---

=== AI ===

Phase 26 — AI Layer

Goal: Augmentation (not replacement)

Features

Graph-aware explanations

Refactoring suggestions

Risk analysis

Natural language queries


Acceptance

Uses core API only

Deterministic core preserved



---

=== OVERLAY EXTENSIONS ===

Phase 27 — Environment Overlay

Goal: Context awareness

Shows

Missing dependencies

Inactive branches

Platform constraints



---

Phase 28 — Dependency Overlay

Goal: Dependency structure visibility


---

Phase 29 — Deployment Overlay

Goal: Execution context visibility


---

Final Architecture

Code
 → AST
 → CFG
 → Symbol Index
 → Metrics
 → Overlay
 → UI

Execution Targets (venv/docker/ssh/k8s)
 → Tooling (lint/test/profile)

Plugins
AI (via core)


---

Key Rules

1. Core must not depend on UI


2. Execution via unified contract


3. Environment is source of truth


4. Overlay is independent layer


5. AI only after deterministic core




---

Final Result

> A modular platform for deep structural analysis of Python code with real execution context