> **Language / Мова:** English | [Українська](../uk/technology/taint-mvp.md)

# Function-local taint MVP (R143 / R227 / R239)

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
| Branches | `if` / `try` / `match` clone env per arm; **may-taint union** on join (R227) |
| Forward CFG (R239) | Statement lists analyzed **once** (no whole-list re-exec). Loop bodies use a local monotone fixpoint on the back-edge. `try` handlers join pre-try + post-statement throw points. Non-exhaustive `match` joins no-match fallthrough. Loop `else` uses normal-termination state (joined with zero-iteration entry). |
| Clearing | Assignment from a clean expression removes taint on that path; join keeps taint if any arm retains it |

## Explicitly out of scope

Interprocedural flow, field-sensitive keys, precise exception / `break`
edges, import-alias resolution beyond dotted callee strings, full
comprehension CFG modeling, `*args`/`**kwargs` fidelity.

## Example

```python
from core.taint import analyze_function_taint

report = analyze_function_taint("def f(x):\n    eval(x)\n", function="f")
assert report.findings[0].source == "param:x"
assert report.findings[0].sink == "eval"
```

Tests: `tests/test_taint.py`, `tests/test_taint_r239.py`.
