> **Language / Мова:** English | [Українська](../uk/technology/taint-mvp.md)

# Function-local taint MVP (R143)

Headless API: `core.taint.analyze_function_taint` /
`analyze_function_taint_from_file`.

## Supported subset

| Area | Behavior |
|------|----------|
| Scope | One `FunctionDef` / `AsyncFunctionDef` (by name, or first in module; class methods by name) |
| Sources | Formal parameters; calls in `DEFAULT_SOURCE_CALLS` (`input`, `sys.stdin.read` / `readline`) |
| Sinks | Calls in `DEFAULT_SINK_CALLS` (`eval`/`exec`, `os.system`/`popen`, `subprocess.*`) |
| Propagation | Name-based, path-insensitive union; assignments; `for` targets; operators; containers; attribute/subscript; call returns if any arg tainted |
| Clearing | Assignment from a clean expression removes taint from simple name targets |

## Explicitly out of scope

Interprocedural flow, field-sensitive keys, exception edges, import-alias
resolution beyond dotted callee strings, full comprehension/CFG modeling,
`*args`/`**kwargs` fidelity.

## Example

```python
from core.taint import analyze_function_taint

report = analyze_function_taint("def f(x):\n    eval(x)\n", function="f")
assert report.findings[0].source == "param:x"
assert report.findings[0].sink == "eval"
```

Tests: `tests/test_taint.py`.
