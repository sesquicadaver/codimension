# TODO_FIXME — Список виявлених проблем для виправлення

> **Мова / Language:** Українська | [English](TODO_FIXME.en.md)

**Дата перевірки:** 2026-08-28 (статичний аудит Alpha @ `master@76342420`; попередній аудит P0–P2 закритий @ d8f2e786 / PR #40)  
**Проєкт:** форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Активний: https://github.com/sesquicadaver/codimension

## Відкриті блокери (аудит 2026-08-28)

Підтверджених **P0** у переглянутому коді немає. P1 A201–A210 закриті. Аудит 2026-09-05 (`codi-last.md` @ 340e97dc): P1-02…P1-08 → R209–R213 ✅; P1-09 → **R214** ✅; наступний OPEN — **R215**.

### Аудит 2026-09-05 (`codi-last.md`) — P1 черга

| ID | Проблема | Пріоритет | Статус |
|----|----------|-----------|--------|
| P1-02 | LSP: немає didChange/didClose; stale `_opened` після restart | P1 | ✅ R209 |
| P1-03 | LSP: немає обробки server→client requests | P1 | ✅ R210 |
| P1-06 | SSH: host-key pin перевіряється після authentication | P1 | ✅ R211 |
| P1-08 | SSH Debug: empty reverse-bind; path `..` escape; busy poll | P1 | ✅ R212 |
| P1-07 | SSH: `binding.json` без перевірки vs cache/profile | P1 | ✅ R213 |
| P1-09 | MCP: довільний локальний каталог без immutable root / budgets | P1 | ✅ R214 |
| P1-04+ | updater / CFG / FFI / AI / reload / plugins | P1 | 🔓 R215–R220 |

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
