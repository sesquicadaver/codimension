> **Language / Мова:** English | [Українська](../uk/technology/taint-mvp.md)

# Function-local taint MVP (R143 / R227 / R239 / R258 / R267)

Headless API: `core.taint.analyze_function_taint` /
`analyze_function_taint_from_file`.

## Supported subset

| Area | Behavior |
|------|----------|
| Scope | One `FunctionDef` / `AsyncFunctionDef` (by name, or first in module; class methods by name) |
| Sources | Formal parameters; calls in `DEFAULT_SOURCE_CALLS` (`input`, `sys.stdin.read` / `readline`) |
| Sinks | Calls in `DEFAULT_SINK_CALLS` (`eval`/`exec`, `os.system`/`popen`, `subprocess.*`) |
| Propagation | Name-based; assignments; `for` targets; operators; containers; attribute/subscript; call returns if any arg tainted |
| Parameters | All formals including `posonlyargs` (R227) |
| Branches (R227 / R258 / R267) | `if` / `try` / `match` clone env per arm and return an **`ExitKind → env` map**. Fall-through uses `NORMAL` only; `return` / `break` / `continue` / `raise` bubble to enclosing lists (nested loops no longer lose outer breaks). |
| `try` / `finally` (R267) | `finally` is analyzed **per reaching exit edge**; a normal `finally` preserves the original exit kind with the post-`finally` environment. |
| Forward CFG (R239 / R258) | Statement lists analyzed **once** (no whole-list re-exec). Loop bodies use a local monotone fixpoint on the back-edge (`continue` + normal end). `try` handlers join pre-try + post-statement throw points. Non-exhaustive `match` joins no-match fallthrough. Loop `else` uses the iteration-boundary head; `break` skips `else` but still joins after the loop. |
| Clearing | Assignment from a clean expression removes taint on that path; join keeps taint if any **NORMAL** arm retains it |

## Explicitly out of scope

Interprocedural flow, field-sensitive keys, full exception CFG precision,
import-alias resolution beyond dotted callee strings, full
comprehension CFG modeling, `*args`/`**kwargs` fidelity.

## Example

```python
from core.taint import analyze_function_taint

report = analyze_function_taint("def f(x):\n    eval(x)\n", function="f")
assert report.findings[0].source == "param:x"
assert report.findings[0].sink == "eval"
```

Tests: `tests/test_taint.py`, `tests/test_taint_r239.py`, `tests/test_taint_r258.py`,
`tests/test_taint_r267.py`.
