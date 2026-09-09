> **Language / Мова:** [English](../../technology/taint-mvp.md) | Українська

# Function-local taint MVP (R143 / R227 / R239 / R258)

Headless API: `core.taint.analyze_function_taint` /
`analyze_function_taint_from_file`.

## Підтримувана підмножина

| Область | Поведінка |
|---------|-----------|
| Scope | Одна `FunctionDef` / `AsyncFunctionDef` (за ім’ям або перша в модулі; методи класу за ім’ям) |
| Sources | Формальні параметри; виклики з `DEFAULT_SOURCE_CALLS` (`input`, `sys.stdin.read` / `readline`) |
| Sinks | Виклики з `DEFAULT_SINK_CALLS` (`eval`/`exec`, `os.system`/`popen`, `subprocess.*`) |
| Propagation | За іменами; присвоєння; цілі `for`; оператори; контейнери; attribute/subscript; повернення виклику, якщо будь-який аргумент tainted |
| Parameters | Усі формальні, включно з `posonlyargs` (R227) |
| Branches (R227 / R258) | `if` / `try` / `match` клонують env; **may-taint union** на join лише для **NORMAL** виходів (`return` / `break` / `continue` / `raise` не входять у fall-through) |
| Forward CFG (R239 / R258) | Списки statements аналізуються **один раз** (без whole-list re-exec). Тіла циклів — локальний monotone fixpoint на back-edge (`continue` + normal end). Handlers `try` об’єднують pre-try + throw points після statements. Неповний `match` додає no-match fallthrough. `else` циклу бачить iteration-boundary head; `break` пропускає `else`, але join після циклу зберігає break-виходи. |
| Clearing | Присвоєння з «чистого» виразу знімає taint на шляху; join зберігає taint, якщо будь-яке **NORMAL** плече його тримає |

## Поза scope

Міжпроцедурний потік, field-sensitive ключі, повна точність exception CFG,
alias імпортів поза dotted callee, повні comprehension CFG, точність
`*args`/`**kwargs`.

## Приклад

```python
from core.taint import analyze_function_taint

report = analyze_function_taint("def f(x):\n    eval(x)\n", function="f")
assert report.findings[0].source == "param:x"
assert report.findings[0].sink == "eval"
```

Тести: `tests/test_taint.py`, `tests/test_taint_r239.py`, `tests/test_taint_r258.py`.
