# Parser Contract — Codimension Pure-Python Parsers

> **Language / Мова:** English | [Українська](../uk/technology/parser-contract.md)

**Status:** normative for `brief_ast` / `flow_ast` (shim modules `cdmpyparser` / `cdmcfparser`)  
**Python:** 3.10–3.13  
**Plan refs:** T001+, `.omx/plans/linear-remediation-atomic-20260802.md`  
**Date:** 2026-08-02

This document is the single source of truth for parser correctness. Implementation must match tests in `tests/conformance/` and `tests/test_source_spans.py`. Where legacy C-extension behaviour disagrees with this contract, **this contract wins**; module **names** of the shims are preserved.

---

## 1. Roles

| Parser | Shim name | Responsibility |
|--------|-----------|----------------|
| `codimension.parsers.brief_ast` | `cdmpyparser` | Brief module model: imports, globals, classes, functions, attributes, docstrings, encoding |
| `codimension.parsers.flow_ast` | `cdmcfparser` | Control-flow fragment tree for Flow UI |

---

## 2. Source encoding

1. File open **must** use `tokenize.open(path)` (PEP 263 encoding cookies).
2. In-memory APIs receive a decoded `str` (Unicode).
3. `open(..., encoding="utf-8", errors="replace")` is **forbidden** for parser entry points (silent corruption).

---

## 3. Spans and positions

### 3.1 Python AST offsets

Per [Python `ast` docs](https://docs.python.org/3/library/ast.html):

- `lineno` / `end_lineno`: 1-based line numbers.
- `col_offset` / `end_col_offset`: **UTF-8 byte offsets** within the line.
- `end_col_offset` points **one byte past** the last character of the node (exclusive end in byte space).

### 3.2 Codimension absolute positions

Shared helper: `codimension.parsers.source_spans` (T003).

| Field | Meaning |
|-------|---------|
| `begin` | 0-based **character** index into the decoded source string (Unicode code points / `str` indices) |
| `end` | 0-based **exclusive** character index: slice `source[begin:end]` is the node text |
| `beginLine` / `endLine` | 1-based line numbers |
| `beginPos` / `endPos` | 1-based **character** columns within the line (UI-facing) |

**Rules:**

1. Build a **line-start index once** per parse (`O(source)`), never re-`split` per node.
2. Convert AST byte offsets → character offsets using UTF-8 of that line.
3. **No `end + 1`** after exclusive conversion.
4. Multibyte characters before a node must not shift later nodes.
5. Prefer `ast.get_source_segment(source, node)` when only the text slice is needed.

### 3.3 Legacy bug (must fix)

Current `flow_ast._pos` / `brief_ast._abs_pos` treat `col_offset` as character index and use inclusive `end` with `end+1` overshoot. That behaviour is **non-compliant** with this contract.

---

## 4. Brief model contract (`brief_ast`)

### 4.1 Functions

- Both `ast.FunctionDef` and `ast.AsyncFunctionDef` must produce function entries at every dispatch site (module, class body, nested in functions and control-flow bodies).
- `isAsync` is `True` iff `AsyncFunctionDef`.

### 4.2 Arguments

- All of: positional-only (`posonlyargs`), regular `args`, `vararg`, keyword-only (`kwonlyargs`), `kwarg`.
- Defaults map to the **corresponding** trailing positional args (not repeatedly to `arguments[-1]`).
- `kw_defaults` map 1:1 to `kwonlyargs` (missing default → `None` / empty value per existing `Argument` API).
- Annotations preserved on arguments when present.

### 4.3 Class / instance attributes

- **Instance attributes:** assignments to `self.NAME` or `cls.NAME` (Name load of first param) via `Assign` / `AnnAssign` / `AugAssign` targets that are `ast.Attribute`.
- Local `Name` stores in methods are **not** instance attributes.
- Class body `Assign` / `AnnAssign` to plain names → class attributes.
- Nested functions and attributes inside `if`/`for`/`try`/`with`/`match` must still be collected.

### 4.4 Assignments

- `AnnAssign`, `AugAssign`, tuple/list unpacking, and chained assignment must not silently drop names required by the brief UI (at minimum: all simple `Name` targets and `self`/`cls` attributes).

### 4.5 Grammar matrix (must not silent-drop)

| Construct | Brief | Flow |
|-----------|-------|------|
| `async def` | required | required |
| `async for` / `async with` | n/a / nested collect | same numeric kind + `isAsync=True`; `withItems` for structured with |
| pos-only / kw-only | required | via function header |
| `match` / `case` | nested collect | dedicated kinds (T023) |
| `try` / `except*` | nested collect | `TRY` / try-star kind (T024) |
| comprehensions | nested if any defs | structured or documented generic with full span |

---

## 5. Flow fragment contract (`flow_ast`)

### 5.1 Existing kinds (keep numeric IDs)

Constants in `flow_ast.py` (`FUNCTION_FRAGMENT`, `IF_FRAGMENT`, …) remain stable for UI compatibility.

### 5.2 New / clarified kinds (implementation tasks)

| Construct | Requirement |
|-----------|-------------|
| `match` / `case` | Not silent `CODEBLOCK` only — dedicated kind(s) or documented extension IDs in Living Spec |
| `except*` / `TryStar` | Distinct from plain `TRY` |
| Module docstring | Once as `DOCSTRING_FRAGMENT`; must not also appear as `CODEBLOCK` |
| Function/class docstring | Populate fragment docstring fields; not only generic Expr |
| Comments / CML / shebang / encoding | Recover via `tokenize`; fill `leadingComment` / `sideComment` / CML lists |

### 5.3 Comments and CML

- Parser must use `tokenize` (not AST alone) to recover comments.
- Attachment rules: leading (no blank line before next stmt), side (same line), independent (blank-line separated) — align with `doc/technology` / CML docs.
- Empty comment fields after a successful parse of commented source are **non-compliant**.

---

## 6. Performance

- Position mapping: `O(source + nodes)`, not `O(nodes × lines)`.
- Live typing path must reuse precomputed line tables per parse invocation.

---

## 7. Testing contract

Conformance suites under `tests/conformance/` are authoritative:

- Brief helpers / cases (async, defaults, attrs, unicode, nested scopes).
- Flow golden snapshots (stable serialization of kind + spans + display + children).
- `source_spans` unit tests (ASCII, Cyrillic prefix, emoji, multi-statement lines).
- Optional differential vs C extensions (`T029`) when wheels are present.

A green CI `pytest` without these suites does **not** imply parser readiness.

---

## 8. Non-goals for this contract

- UI redesign of Flow chrome.
- Removing shim module names.
- Perfect parity with every historical C-parser quirk when it contradicts correctness above.

---

## 9. Change control

Any change to span inclusivity, kind IDs, or brief field semantics:

1. Update this document (en + uk).
2. Update Living Spec rows.
3. Update / regenerate conformance snapshots.
4. Run T028.1 Flow UI coupling smoke when spans change.
