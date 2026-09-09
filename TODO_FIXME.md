# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-09-09 (статичний аудит @ `master@eaa3dfee` / `codi-last.md`; хвилі R209–R251 закриті)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери (аудит 2026-09-09)

Підтверджених **P0** немає. **P1: 3** відкритих груп → **R253–R255**. **P2: 7** груп → **R256–R260**. Хвиля R232–R252 ✅; зріз `codi-last.md` @ master@eaa3dfee.

### Повторний аудит 2026-09-09 (`codi-last.md` @ eaa3dfee) — P1 черга

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P1-01 | LSP: application request після `ensure_initialized` може піти в новий transport до handshake | P1 | ✅ R252 |
| P1-02 | LSP semantic: `didOpen/didChange` і `request` не в одній generation | P1 | 🔓 OPEN → **R253** |
| P1-03 | Plugin package identity fail-open для oversized/unreadable member (`package_sha256=""`) | P1 | 🔓 OPEN → **R254** |
| P1-04 | SSH fallback replace: фіксовані staging/backup імена; не crash/concurrency-safe | P1 | 🔓 OPEN → **R255** |

### P2 / технічний борг (аудит 2026-09-09)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P2-01 | LSP pending leak при encode/write failure | P2 | 🔓 OPEN → **R256** |
| P2-02 | URI: NUL у percent-decode; direct loader може обійти `O_NOFOLLOW` | P2 | 🔓 OPEN → **R256** |
| P2-03 | Project switch: unload без rollback після `before_load` | P2 | 🔓 OPEN → **R257** |
| P2-04 | Taint: terminal branch environment у звичайному join | P2 | 🔓 OPEN → **R258** |
| P2-05 | AI evidence не прив’язане до declared line range | P2 | 🔓 OPEN → **R259** |
| P2-06 | AI budget parser приймає `NaN` / non-finite | P2 | 🔓 OPEN → **R259** |
| P2-07 | CI coverage floor 30% все ще низький | P2 | 🔓 OPEN → **R260** |

### Повторний аудит 2026-09-08 (`codi-last.md` @ 645d655) — P1 черга (закрита)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P1-01 | LSP: pending+write не атомарні з transport generation; старі server→client msgs забруднюють новий process | P1 | ✅ R244 |
| P1-02 | Editor semantic snapshot `version=0` регресує DocumentStore/LSP; Save As без close(old) | P1 | ✅ R245 |
| P1-03 | UI ігнорує UNRESOLVED; percent-encoded URI stale disk; loader FIFO/TOCTOU | P1 | ✅ R246 |
| P1-04 | MCP: `sorted(scandir)` матеріалізує весь каталог до `max_entries` | P1 | ✅ R247 |
| P1-05 | SSH Save: Paramiko `rename` не замінює існуючий dest (потрібен posix_rename/swap) | P1 | ✅ R248 |
| P1-06 | AI cost budget: provider `max_tokens` може перевищити cost remainder | P1 | ✅ R249 |
| P1-07 | pybind11 EXACT без CST `.def()` call_expression (regex у module body) | P1 | ✅ R250 |

### P2 / технічний борг (аудит 2026-09-08) — закритий

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P2-01…06 | AI finding wrong file; plugin package identity; non-transactional switch; terminal taint; R242 editor gaps; CI floor | P2 | ✅ R251 |

### Повторний аудит 2026-09-07 (`codi-last.md` @ 45e33f6) — P1 черга (закрита)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P1-01 | Plugin re-enable: `materializePlugin` → `loadPlugins()` без повторної manifest/file-identity перевірки | P1 | ✅ R232 |
| P1-02 | LSP: після crash request може піти до нового `initialize` | P1 | ✅ R233 |
| P1-03 | LSP: race/`InvalidStateError` у `_pending` без lock + generation | P1 | ✅ R234 |
| P1-04 | DocumentStore: falsy empty store, stale disk, `(0,0)`, unversioned edits, unbounded loader | P1 | ✅ R235 |
| P1-05 | Create Project обходить R230 lifecycle (`createNew` без ApplicationServices) | P1 | ✅ R236 |
| P1-09 | AI HTTP: redirects без re-validate trust (як Updater R222) | P1 | ✅ R237 |
| P1-08 | MCP walker: unbounded `listdir` + TOCTOU path escape | P1 | ✅ R238 |
| P1-07 | Taint: whole-list re-exec → sink-before-source; exception/match/loop-else gaps | P1 | ✅ R239 |
| P1-06 | FFI `EXACT`: structural proof не завжди edge-specific identity | P1 | ✅ R240 |
| P1-10 | AI budgets soft; немає cancel/deadline/evidence hard validation | P1 | ✅ R241 |

### P2 / технічний борг (аудит 2026-09-07) — закритий

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P2-01 | Polyglot controller не підключений до editor actions; Python stub vs `supports()` | P2 | ✅ R242 |
| P2-02…07 | File URI encoding; risk confidence vs custom weights; SSH upload unbounded; CI coverage/Bandit; Actions pins; docs drift | P2 | ✅ R243 |

### Аудит 2026-09-05 (`codi-last.md` @ 340e97dc) — P1 черга (закрита)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P1-02 | LSP: немає didChange/didClose; stale `_opened` після restart | P1 | ✅ R209 |
| P1-03 | LSP: немає обробки server→client requests | P1 | ✅ R210 |
| P1-06 | SSH: host-key pin перевіряється після authentication | P1 | ✅ R211 |
| P1-08 | SSH Debug: empty reverse-bind; path `..` escape; busy poll | P1 | ✅ R212 |
| P1-07 | SSH: `binding.json` без перевірки vs cache/profile | P1 | ✅ R213 |
| P1-09 | MCP: довільний локальний каталог без immutable root / budgets | P1 | ✅ R214 |
| P1-10 | Updater: SHA-256 без provenance; unbounded read; broken version probe | P1 | ✅ R215 |
| P1-11 | CFG: loop-else bypass + non-exhaustive match без no-match edge | P1 | ✅ R216 |
| P1-05 | FFI: `EXACT` без повного registration chain | P1 | ✅ R217 |
| P1-13 | AI docstring apply: wrong symbol / corrupt code | P1 | ✅ R218 |
| P1-15 | External `.cdm3` reload split-brain / UUID | P1 | ✅ R219 |
| P1-16 | Plugin capability policy після import | P1 | ✅ R220 |

### Повторний аудит 2026-09-06 (`codi-last.md` @ 8824ff3c) — P1 черга (закрита)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P1-01 | SSH binding: `local_root` ≠ `remote_cache_dir(profile, remote_root)` | P1 | ✅ R221 |
| P1-02 | Updater: redirect chain без re-validate trust | P1 | ✅ R222 |
| P1-03 | MCP budgets після необмеженого traversal | P1 | ✅ R223 |
| P1-04 | Cross-file LSP locations → `SourceSpan(0,0)` | P1 | ✅ R224 |
| P1-07 | Plugin pre-import policy ще fail-open (legacy fallback) | P1 | ✅ R225 |
| P1-06 | FFI `EXACT` без structural registration proof | P1 | ✅ R226 |
| P1-08 | Taint: немає `posonlyargs`; branch env overwrite | P1 | ✅ R227 |
| P1-09 | Blank UUID після load → identity drift | P1 | ✅ R228 |
| P1-05 | Polyglot capabilities ≠ provider API | P1 | ✅ R229–R230 |
| P1-AI | AI prose synthesis без Finding/budgets | P1 | ✅ R231 |

### UX hardening (поза ROADMAP-чергою)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| UX-SCAN | Повільний скан великих дерев без пропозиції ignore | P2 | ✅ 30s prompt + `excludeFromProjectTree` |
| UX-DRAWLINE | qutepart `paintEvent` / whitespace: `drawLine` float mid-Y → TypeError (PyQt5) | P1 | ✅ override paint (no QPainter monkeypatch; sip QLineF safe) |
| UX-DRAWLINE2 | After #152 monkeypatch, flow UI `painter.drawLine(QLineF)` → unbound TypeError | P0 | ✅ remove monkeypatch; int coords in override |
| UX-DOCSPAN | flow_ast `_DocstringFrag` без `beginLine`/`body` → crash hide-comments | P0 | ✅ spans з AST stmt |
| UX-PYLINT-TB | pylint `sigFileTypeChanged` → `ImportDgmTabWidget` без `toolbar` | P1 | ✅ bundled pylint 1.0.5 + `editor_toolbar` |

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| A201 | SSH: `profile.id` / project name без path-containment → `_rm_tree`/write поза cache | P1 | ✅ R183 |
| A202 | SSH: `AutoAddPolicy` — host authenticity вимкнена (MITM) | P1 | ✅ R184 |
| A203 | SSH download: `stat` замість `lstat`, symlink follow, unlimited defaults, no staging swap | P1 | ✅ R185 |
| A204 | SSH Run/Save блокують GUI; немає cancel/timeout/output cap; Save≠SYNCED | P1 | ✅ R186 |
| A205 | `ExecutionTarget.run` = prepare argv (`exit_code=None`), не виконання | P1 | ✅ R187 |
| A206 | Kubernetes: wait Ready ≠ Complete; hash argv; cleanup не в finally | P1 | ✅ R187 |
| A207 | CFG: global EXIT; break/continue без loop stack; непридатний для data-flow/security | P1 | ✅ R188 |
| A208 | VENV: rename staging→final ламає shebang/activate (попереднє D02/B07 недостатнє) | P1 | ✅ R189 |
| A209 | Зовнішнє оновлення `.cdm3`: split-brain; UUID mutable після load | P1 | ✅ R190 |
| A210 | Plugin policy після `import` plugin code (не fail-closed) | P1 | ✅ R191 |

### P2 / hardening (активна хвиля ROADMAP R192–R197)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| A220 | AI: `response.read()` до limit; немає budget/cancel; keyed `base_url` без trust policy | P2 | ✅ R192 |
| A221 | Settings: валідний JSON не-dict ламає startup; import-time singleton | P2 | ✅ R193 |
| A222 | Taint/risk: евристика; missing metrics → штучно низький risk | P2 | ✅ R194 |
| A223 | Архітектура: `utils` side-effects; boundary gate не інвертує залежності | P2 | ✅ R195–R196 |
| A224 | Smoke: `os._exit(0)` без normal shutdown; constraints/wrapt drift | P2 | ✅ R197 |

## Закриті (історичний аудит)

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| B01 / B02 / C01 / D01 | VENV identity/UUID/destination/base combo | P0–P1 | ✅ |
| D03 | Redirected argv + `shell=False` | P1 | ✅ (redirected) |
| E01 / E02 | Custom-terminal launcher `${prog}` + Profile cProfile | P1 | ✅ |
| E04 / F07 | Stale cleanup symlink traversal у `/tmp` | P1 | ✅ |
| E04 (штатний unlink) | Launcher cleanup до execvp | P1 | ✅ |
| E05 | Profile timeout від shell `&` евристики; orphan `.done` | P1 | ✅ |
| E06 | noexec execute-probe; обмеження shell-safe paths | P1 | ✅ |
| D02 / B07 | VENV staging+commit (MVP) | P1 | ✅ (superseded by A208 / R189) |
| C02 / C03 | Interpreter probe; recreate=`sys.executable` | P1 | ✅ |
| B03 | Project scan cancel/join/coalescing | P1 | ✅ |
| B04 | brief keyword/name/colon + target/alias positions | P1 | ✅ |
| D05 | Encoding cookie на 2-му рядку після false «coding» | P1 | ✅ |
| B05 / D04 | CML clustering + indentation scopes | P1 | ✅ |
| B06 | `case` keyword через `rfind` | P1 | ✅ |
| D06 | Side comments багаторядкових headers | P1 | ✅ |
| D07 / B08 | Production startup + plugin load | P1 | ✅ |
| C04 | Flow UI import → `pytest.skip` | P1 | ✅ |
| B11 | Docs drift | P2 | ✅ |
| B09 / B10 / C05 | Schema paths / atomic settings / UUID persist | P2 | ✅ |
| D08 / E03 / G01 | Constraints / release verify / branch protection | P2 | ✅ |

## Інфраструктура

| Тема | Стан |
|------|------|
| **CI** | перевіряти latest green Actions на HEAD (не static count у README) |
| **Docs gate** | `python scripts/check_docs.py` (links/images/dirs/anchors/ref/HTML; UA↔EN; TODO↔Living Spec; CI matrix) |
| **Nightly full-IDE** | weekly, не PR-blocker |
| **Living Spec** | матриця модулів; без static SHA/test count |
| **Статус продукту** | Alpha — remote execution / CFG-as-proof не production-ready |

Жива матриця: [doc/plugins/living-specification.md](doc/plugins/living-specification.md).
