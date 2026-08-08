> **Language / Мова:** [English](../../technology/taint-mvp.md) | Українська

# Function-local taint MVP (R143)

Headless API: `core.taint.analyze_function_taint` /
`analyze_function_taint_from_file`.

## Підтримувана підмножина

| Область | Поведінка |
|---------|-----------|
| Scope | Одна `FunctionDef` / `AsyncFunctionDef` (за ім’ям або перша в модулі; методи класу за ім’ям) |
| Sources | Формальні параметри; виклики з `DEFAULT_SOURCE_CALLS` (`input`, `sys.stdin.read` / `readline`) |
| Sinks | Виклики з `DEFAULT_SINK_CALLS` (`eval`/`exec`, `os.system`/`popen`, `subprocess.*`) |
| Propagation | За іменами, path-insensitive union; присвоєння; цілі `for`; оператори; контейнери; attribute/subscript; повернення виклику, якщо будь-який аргумент tainted |
| Clearing | Присвоєння з «чистого» виразу знімає taint з простих імен |

## Поза scope

Міжпроцедурний потік, field-sensitive ключі, exception edges, alias імпортів
поза dotted callee, повні comprehension/CFG, точність `*args`/`**kwargs`.

## Приклад

```python
from core.taint import analyze_function_taint

report = analyze_function_taint("def f(x):\n    eval(x)\n", function="f")
assert report.findings[0].source == "param:x"
assert report.findings[0].sink == "eval"
```

Тести: `tests/test_taint.py`.
