# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-28 (static Alpha audit @ `master@76342420`; prior P0–P2 audit closed @ d8f2e786 / PR #40)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (2026-08-28 audit)

No confirmed **P0** in the reviewed code. P1 A201–A210 closed. ROADMAP queue: **R182→**.

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| A201 | SSH: `profile.id` / project name path-containment → `_rm_tree`/write outside cache | P1 | ✅ R183 |
| A202 | SSH: `AutoAddPolicy` — host authenticity disabled (MITM) | P1 | ✅ R184 |
| A203 | SSH download: `stat` not `lstat`, symlink follow, unlimited defaults, no staging swap | P1 | ✅ R185 |
| A204 | SSH Run/Save block GUI; no cancel/timeout/output cap; Save≠SYNCED | P1 | ✅ R186 |
| A205 | `ExecutionTarget.run` = prepare argv (`exit_code=None`), not execute | P1 | ✅ R187 |
| A206 | Kubernetes: wait Ready ≠ Complete; argv hash; cleanup not in finally | P1 | ✅ R187 |
| A207 | CFG: global EXIT; break/continue without loop stack; unfit for data-flow/security | P1 | ✅ R188 |
| A208 | VENV: staging→final rename breaks shebang/activate (prior D02/B07 insufficient) | P1 | ✅ R189 |
| A209 | External `.cdm3` update: split-brain; UUID mutable after load | P1 | ✅ R190 |
| A210 | Plugin policy after importing plugin code (not fail-closed) | P1 | ✅ R191 |

### P2 / hardening (active ROADMAP wave R192–R197)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| A220 | AI: full `response.read()` before limit; no budget/cancel; keyed `base_url` trust | P2 | ✅ R192 |
| A221 | Settings: non-dict JSON breaks startup; import-time singleton | P2 | ✅ R193 |
| A222 | Taint/risk heuristic; missing metrics understate risk | P2 | ✅ R194 |
| A223 | Architecture: `utils` side-effects; boundary gate does not invert deps | P2 | ✅ R195–R196 |
| A224 | Smoke: `os._exit(0)` skips shutdown; constraints/wrapt drift | P2 | ✅ R197 |

## Closed (historical audit)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| B01 / B02 / C01 / D01 | VENV identity/UUID/destination/base combo | P0–P1 | ✅ |
| D03 | Redirected argv + `shell=False` | P1 | ✅ (redirected) |
| E01 / E02 | Custom-terminal launcher `${prog}` + Profile cProfile | P1 | ✅ |
| E04 / F07 | Stale cleanup symlink traversal under `/tmp` | P1 | ✅ |
| E04 (routine unlink) | Launcher cleanup before execvp | P1 | ✅ |
| E05 | Profile timeout from shell `&` heuristic; orphan `.done` | P1 | ✅ |
| E06 | noexec execute-probe; shell-safe path limits | P1 | ✅ |
| D02 / B07 | VENV staging+commit (MVP) | P1 | ✅ (superseded by A208 / R189) |
| C02 / C03 | Interpreter probe; recreate=`sys.executable` | P1 | ✅ |
| B03 | Project scan cancel/join/coalescing | P1 | ✅ |
| B04 | brief keyword/name/colon + target/alias positions | P1 | ✅ |
| D05 | Encoding cookie on line 2 after false “coding” | P1 | ✅ |
| B05 / D04 | CML clustering + indentation scopes | P1 | ✅ |
| B06 | `case` keyword via `rfind` | P1 | ✅ |
| D06 | Side comments on multi-line headers | P1 | ✅ |
| D07 / B08 | Production startup + plugin load | P1 | ✅ |
| C04 | Flow UI import → `pytest.skip` | P1 | ✅ |
| B11 | Docs drift | P2 | ✅ |
| B09 / B10 / C05 | Schema paths / atomic settings / UUID persist | P2 | ✅ |
| D08 / E03 / G01 | Constraints / release verify / branch protection | P2 | ✅ |

## Infrastructure

| Topic | State |
|------|-------|
| **CI** | use latest green Actions on HEAD (no static count in README) |
| **Docs gate** | `python scripts/check_docs.py` |
| **Nightly full-IDE** | weekly, not a PR blocker |
| **Living Spec** | module matrix; no static SHA/test count |
| **Product status** | Alpha — remote execution / CFG-as-proof not production-ready |

Living matrix: [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).
