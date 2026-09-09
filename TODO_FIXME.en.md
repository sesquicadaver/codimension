# TODO_FIXME — Issues to fix

> **Language / Мова:** English | [Українська](TODO_FIXME.md)

**Last review:** 2026-09-09 (static audit @ `master@f44c8dc4` / `codi-last.md`; waves R209–R260 integrated)  
**Project:** fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Active: https://github.com/sesquicadaver/codimension

## Open blockers (2026-09-09 audit @ f44c8dc4)

No confirmed **P0**. **P1: 2** groups → **R263–R264**. **P2: 5** groups → **R265–R268**. Wave R252–R260 integrated with residuals; slice `codi-last.md` @ master@f44c8dc4.

### Re-audit 2026-09-09 (`codi-last.md` @ f44c8dc4) — P1 queue

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P1-01 | SSH replace: crash between `dest→backup` and `dest_moved` → `staged` recovery destroys sole valid copy | P1 | ✅ R261 |
| P1-02 | R253: `notify()` lacks `expect_generation` → `didChange` on new generation without `didOpen` | P1 | ✅ R262 |
| P1-03 | DocumentStore: URI alias (`file://localhost`) can replace `OPEN_BUFFER` with disk `DISK` | P1 | 🔓 OPEN → **R263** |
| P1-04 | Plugin identity: symlinked directories omitted from `package_sha256` but still importable | P1 | 🔓 OPEN → **R264** |

### P2 / tech debt (2026-09-09 audit @ f44c8dc4)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P2-01 | Project lifecycle: `unload` outside rollback `try`; `before_unload` may detach workspace without restore | P2 | 🔓 OPEN → **R265** |
| P2-02 | LSP reader EOF does not invalidate transport; workers hold mutable `self._proc` | P2 | 🔓 OPEN → **R266** |
| P2-03 | LSP range decoder throws on malformed position instead of `UNRESOLVED` | P2 | 🔓 OPEN → **R266** |
| P2-04 | Taint: single ExitKind/env; terminal envs lost before `finally`; nested loop collectors | P2 | 🔓 OPEN → **R267** |
| P2-05 | AI explicit kwargs (`deadline_sec=NaN`/negative) not fail-closed like env parser | P2 | 🔓 OPEN → **R268** |

### Wave R252–R260 status (slice f44c8dc4)

| Task | Result |
|------|--------|
| R252 | ✅ Closed |
| R253 | ✅ Closed (residual R262) |
| R254 | ⚠️ Partial → residual **R264** |
| R255 | ⚠️ Incomplete → residual **R261** |
| R256 | ✅ Closed |
| R257 | ⚠️ Partial → residual **R265** |
| R258 | ⚠️ Partial → residual **R267** |
| R259 | ⚠️ Core ✅; explicit API → **R268** |
| R260 | ✅ Closed as scoped |

### Re-audit 2026-09-09 (`codi-last.md` @ eaa3dfee) — P1 queue (integrated; see residuals above)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P1-01 | LSP: application request after `ensure_initialized` may hit new transport before handshake | P1 | ✅ R252 |
| P1-02 | LSP semantic: `didOpen/didChange` and `request` not in one generation | P1 | ✅ R253 + ✅ R262 |
| P1-03 | Plugin package identity fail-open for oversized/unreadable member (`package_sha256=""`) | P1 | ✅ R254 (residual → R264) |
| P1-04 | SSH fallback replace: fixed staging/backup names; not crash/concurrency-safe | P1 | ✅ R255 (residual → R261) |

### P2 / tech debt (2026-09-09 audit @ eaa3dfee) — integrated

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P2-01 | LSP pending leak on encode/write failure | P2 | ✅ R256 |
| P2-02 | URI: NUL in percent-decode; direct loader may bypass `O_NOFOLLOW` | P2 | ✅ R256 |
| P2-03 | Project switch: unload without rollback after `before_load` | P2 | ✅ R257 (residual → R265) |
| P2-04 | Taint: terminal branch env in normal join | P2 | ✅ R258 (residual → R267) |
| P2-05 | AI evidence not bound to declared line range | P2 | ✅ R259 |
| P2-06 | AI budget parser accepts `NaN` / non-finite | P2 | ✅ R259 (residual → R268) |
| P2-07 | CI coverage floor 30% still low | P2 | ✅ R260 |

### Re-audit 2026-09-08 (`codi-last.md` @ 645d655) — P1 queue (closed)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P1-01 | LSP: pending+write not atomic with transport generation; stale server→client msgs pollute new process | P1 | ✅ R244 |
| P1-02 | Editor semantic snapshot `version=0` regresses DocumentStore/LSP; Save As without close(old) | P1 | ✅ R245 |
| P1-03 | UI ignores UNRESOLVED; percent-encoded URI stale disk; loader FIFO/TOCTOU | P1 | ✅ R246 |
| P1-04 | MCP: `sorted(scandir)` materializes entire directory before `max_entries` | P1 | ✅ R247 |
| P1-05 | SSH Save: Paramiko `rename` does not replace existing dest (need posix_rename/swap) | P1 | ✅ R248 |
| P1-06 | AI cost budget: provider `max_tokens` may exceed cost remainder | P1 | ✅ R249 |
| P1-07 | pybind11 EXACT without CST `.def()` call_expression (regex in module body) | P1 | ✅ R250 |

### P2 / tech debt (2026-09-08 audit) — closed

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P2-01…06 | AI finding wrong file; plugin package identity; non-transactional switch; terminal taint; R242 editor gaps; CI floor | P2 | ✅ R251 |

### Re-audit 2026-09-07 (`codi-last.md` @ 45e33f6) — P1 queue (closed)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P1-01 | Plugin re-enable: `materializePlugin` → `loadPlugins()` without re-check of manifest/file identity | P1 | ✅ R232 |
| P1-02 | LSP: after crash, request may run before new `initialize` | P1 | ✅ R233 |
| P1-03 | LSP: race/`InvalidStateError` in `_pending` without lock + generation | P1 | ✅ R234 |
| P1-04 | DocumentStore: falsy empty store, stale disk, `(0,0)`, unversioned edits, unbounded loader | P1 | ✅ R235 |
| P1-05 | Create Project bypasses R230 lifecycle (`createNew` without ApplicationServices) | P1 | ✅ R236 |
| P1-09 | AI HTTP: redirects without re-validate trust (mirror Updater R222) | P1 | ✅ R237 |
| P1-08 | MCP walker: unbounded `listdir` + TOCTOU path escape | P1 | ✅ R238 |
| P1-07 | Taint: whole-list re-exec → sink-before-source; exception/match/loop-else gaps | P1 | ✅ R239 |
| P1-06 | FFI `EXACT`: structural proof not always edge-specific identity | P1 | ✅ R240 |
| P1-10 | AI budgets soft; no cancel/deadline/evidence hard validation | P1 | ✅ R241 |

### P2 / tech debt (2026-09-07 audit) — closed

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P2-01 | Polyglot controller not wired to editor actions; Python stub vs `supports()` | P2 | ✅ R242 |
| P2-02…07 | File URI encoding; risk confidence vs custom weights; SSH upload unbounded; CI coverage/Bandit; Actions pins; docs drift | P2 | ✅ R243 |

### Audit 2026-09-05 (`codi-last.md` @ 340e97dc) — P1 queue (closed)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P1-02 | LSP: no didChange/didClose; stale `_opened` after restart | P1 | ✅ R209 |
| P1-03 | LSP: no server→client request handling | P1 | ✅ R210 |
| P1-06 | SSH: host-key pin checked after authentication | P1 | ✅ R211 |
| P1-08 | SSH Debug: empty reverse-bind; path `..` escape; busy poll | P1 | ✅ R212 |
| P1-07 | SSH: `binding.json` trusted without cache/profile checks | P1 | ✅ R213 |
| P1-09 | MCP: arbitrary local directory without immutable root / budgets | P1 | ✅ R214 |
| P1-10 | Updater: SHA-256 without provenance; unbounded read; broken version probe | P1 | ✅ R215 |
| P1-11 | CFG: loop-else bypass + non-exhaustive match missing no-match edge | P1 | ✅ R216 |
| P1-05 | FFI: `EXACT` without full registration chain | P1 | ✅ R217 |
| P1-13 | AI docstring apply: wrong symbol / corrupt code | P1 | ✅ R218 |
| P1-15 | External `.cdm3` reload split-brain / UUID | P1 | ✅ R219 |
| P1-16 | Plugin capability policy after import | P1 | ✅ R220 |

### Re-audit 2026-09-06 (`codi-last.md` @ 8824ff3c) — P1 queue (closed)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| P1-01 | SSH binding: `local_root` ≠ `remote_cache_dir(profile, remote_root)` | P1 | ✅ R221 |
| P1-02 | Updater: redirect chain without re-validate trust | P1 | ✅ R222 |
| P1-03 | MCP budgets after unbounded traversal | P1 | ✅ R223 |
| P1-04 | Cross-file LSP locations → `SourceSpan(0,0)` | P1 | ✅ R224 |
| P1-07 | Plugin pre-import policy still fail-open (legacy fallback) | P1 | ✅ R225 |
| P1-06 | FFI `EXACT` without structural registration proof | P1 | ✅ R226 |
| P1-08 | Taint: missing `posonlyargs`; branch env overwrite | P1 | ✅ R227 |
| P1-09 | Blank UUID after load → identity drift | P1 | ✅ R228 |
| P1-05 | Polyglot capabilities ≠ provider API | P1 | ✅ R229–R230 |
| P1-AI | AI prose synthesis without Finding/budgets | P1 | ✅ R231 |

### UX hardening (outside ROADMAP queue)

| ID | Issue | Priority | Status |
|----|-------|----------|--------|
| UX-SCAN | Slow scan of huge trees with no ignore offer | P2 | ✅ 30s prompt + `excludeFromProjectTree` |
| UX-DRAWLINE | qutepart whitespace paint: `drawLine` float mid-Y → TypeError (PyQt5) | P1 | ✅ override paint (no QPainter monkeypatch; sip QLineF safe) |
| UX-DRAWLINE2 | After #152 monkeypatch, flow UI `painter.drawLine(QLineF)` → unbound TypeError | P0 | ✅ remove monkeypatch; int coords in override |
| UX-DOCSPAN | flow_ast `_DocstringFrag` missing `beginLine`/`body` → hide-comments crash | P0 | ✅ spans from AST stmt |
| UX-PYLINT-TB | pylint `sigFileTypeChanged` → `ImportDgmTabWidget` has no `toolbar` | P1 | ✅ bundled pylint 1.0.5 + `editor_toolbar` |

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
