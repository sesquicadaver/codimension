# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-08-06 (audit master@d8f2e786 / PR #40)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (audit @ d8f2e786)

Audit P0–P2 rows in TODO are closed. Further work is the linear atomic queue in [ROADMAP.md](ROADMAP.md) (first OPEN: **R137**).

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| B01 / B02 / C01 / D01 | VENV identity/UUID/destination/base combo | P0–P1 | ✅ |
| D03 | Redirected argv + `shell=False` | P1 | ✅ (redirected) |
| E01 / E02 | Custom-terminal launcher `${prog}` + Profile cProfile | P1 | ✅ |
| E04 / F07 | Stale cleanup symlink traversal under `/tmp` | P1 | ✅ lstat/O_NOFOLLOW + one-shot legacy `/tmp` |
| E04 (routine unlink) | Launcher cleanup before execvp | P1 | ✅ |
| E05 | Profile timeout from shell `&` heuristic; orphan `.done` | P1 | ✅ start deadline + marker cleanup |
| E06 | noexec execute-probe; shell-safe path limits | P1 | ✅ exec probe + DQ-safe paths |
| D02 / B07 | VENV create/recreate without transaction/rollback | P1 | ✅ staging + commit |
| C02 / C03 | Interpreter probe; recreate=`sys.executable` | P1 | ✅ probe + version-matched base |
| B03 | Project scan cancel/join/coalescing | P1 | ✅ interrupt + coalesce + no GUI sync fallback |
| B04 | brief keyword/name/colon + target/alias positions | P1 | ✅ `TokenIndex` + identifier spans |
| D05 | Encoding cookie on line 2 after false “coding” | P1 | ✅ scan both lines until real cookie |
| B05 / D04 | CML clustering + indentation scopes | P1 | ✅ split on indent / CML head / cml+ |
| B06 | `case` keyword via `rfind` | P1 | ✅ `TokenIndex.find_name_before` |
| D06 | Side comments on multi-line headers | P1 | ✅ header line span |
| D07 / B08 | Production startup + plugin load | P1 | ✅ bundled paths + full `imp` + smoke gate |
| C04 | Flow UI import → `pytest.skip` | P1 | ✅ fail on import; only skip missing PyQt5 / TryStar |
| B11 | Docs drift (TODO/Living Spec/`doc/uk`, docs gate coverage) | P2 | ✅ parity + expanded `check_docs` |
| B09 / B10 / C05 | Schema paths / atomic settings / UUID persist | P2 | ✅ validate all paths; atomic flush; uuid4 + immediate save |
| D08 / E03 / G01 | Constraints / release verify / branch protection | P2 | ✅ constraints snapshot; release verify+OIDC; `ci-gate` + master protection |

## Infrastructure

| Topic | State |
|------|-------|
| **CI** | use latest green Actions on HEAD (no static count in README) |
| **Docs gate** | `python scripts/check_docs.py` (links/images/dirs/anchors/ref/HTML; UA↔EN; TODO↔Living Spec; CI matrix) |
| **Nightly full-IDE** | weekly, not a PR blocker |
| **Living Spec** | module matrix; no static SHA/test count |

Living matrix: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
