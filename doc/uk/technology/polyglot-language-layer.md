> **Мова / Language:** Українська | [English](../../technology/polyglot-language-layer.md)

# Polyglot language layer (R200–R208)

Codimension розширюється за межі Python через **універсальний language layer**,
а не окремі «підтримки Rust/C++» і не Yapsy language plugins.

## Чотири незалежні провайдери

| Провайдер | Роль |
| --------- | ---- |
| **LSP (семантика)** | Diagnostics, completion, hover, definitions, references, rename, formatting, semantic tokens |
| **Tree-sitter (структура)** | Інкрементальний синтаксис, outline, structural graph (не compiler CFG) |
| **FFI Binding Index** | Evidence-backed Python API ↔ реалізація Rust/C++ |
| **Task Provider** | Build/test/check — окремо від семантики редактора |

**Не робити:** власні Rust/C++ parsers; перенесення логіки компіляторів у Python;
копіювання Python CFG pipeline на кожну мову; мови як VCS/Wizard plugins.

## Розміщення по шарах

| Частина | Пакет |
| ------- | ----- |
| `LanguageDescriptor`, capabilities, Protocol, Registry | `codimension/core/language.py` |
| Lifecycle manager | `codimension/app/language_services.py` |
| LSP stdio / position codec I/O | `infrastructure` + тонкий `utils` |
| UI controller | `ui/language_controller.py` (лише capability checks) |

UI перевіряє **capabilities**, ніколи `if language == "rust"`.

## SymbolRecord (Stage 1 = additive)

Зберігаємо наявні поля (`name`, `kind: SymbolKind`, `file`, `span`, …). Додаємо
`language_id` (default `"python"`), `generic_kind` і опційно
`symbol_key` / `provider_id` / `native_kind` з безпечними дефолтами. Повний
polyglot multi-index — пізніше (R206+), без поломки MCP/search у Stage 1.

## Position codec

Усередині Codimension — **лише Unicode character offsets**
(`core/document_snapshot.py`). Encoding LSP (UTF-16 / UTF-8 / UTF-32)
залишається за `infrastructure/lsp_position_codec.py` на кожен server process.
Diagnostics і edits несуть document version; застарілі edits відхиляються
(`StaleDocumentEditError`).

## Ключ LSP-процесу

Один процес на `(language_id, workspace_root, toolchain_configuration)` —
наприклад кожен `Cargo.toml` workspace і кожне дерево clangd з
`compile_commands.json`. Реалізація: `infrastructure/lsp_process.py`
(`LspProcess` / `LspProcessRegistry`): lazy start; Content-Length JSON-RPC;
reader thread + serialized writer; `$/cancelRequest`; обмежені stderr ring і
розмір повідомлення; bounded backoff; `initialize` → `shutdown` → `exit` при
unload. Spawn через `core/language_policy.py`
(`LANGUAGE_SERVER_SPAWN`: лише absolute binary з allowlist).

## SemanticProvider (R203)

Rust (`rust-analyzer`) і C++ (`clangd`) реєструються через
`LanguageServiceManager.register_rust_lsp` / `register_cpp_lsp`.
C++ без `compile_commands.json` — **DEGRADED** (немає претензії на
повні diagnostics).

## Security policy (deny-by-default)

Перед side effects — гейти capabilities на кшталт:

`LANGUAGE_SERVER_SPAWN`, `PROJECT_METADATA_EXEC`, `BUILD_SCRIPT_EXEC`,
`PROC_MACRO_EXEC`, `CHECK_COMMAND_EXEC`, `COMPILER_QUERY_EXEC`,
`FORMATTER_EXEC`, `WORKSPACE_EDIT_APPLY`, `BUILD_TASK_EXEC`.

- rust-analyzer build scripts / proc macros / check-on-save: лише explicit allow.
- clangd `--query-driver`: allowlist абсолютних шляхів компілятора.
- Workspace edits: containment, versions, без overlapping, preview, atomic apply.

## Карта етапів (ROADMAP)

| Етап | ID | Поставка |
| ---- | -- | -------- |
| 1 Editor | R200–R204 | Registry, codec, LspProcess, Rust/C++ LSP descriptors, capability UI |
| 2 Structure | R205 | Tree-sitter StructuralGraph + semantic roles |
| 3 FFI | R206–R207 | BindingIndex extractors + dependency edge kinds + cross-nav |
| 4 Tasks | R208 | Cargo / CMake / Ninja / CTest providers |

**Поза хвилею:** DAP/native debug; власні компілятори/parsers; Yapsy language plugins.

## Формула

```text
Python:  наявний аналіз Codimension
Rust:    rust-analyzer + Tree-sitter Rust + PyO3 bridge + Cargo tasks
C++:     clangd + Tree-sitter C++ + pybind11/CPython bridge
         + compile_commands.json + CMake tasks
Shared:  normalized symbols/diagnostics, structural graph,
         typed dependency edges, evidence-backed FFI
```
