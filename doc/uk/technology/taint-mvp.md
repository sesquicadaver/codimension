> **Language / Мова:** [English](../../technology/taint-mvp.md) | Українська

# Function-local taint MVP (R143 / R227 / R239)

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
| Branches | `if` / `try` / `match` клонують env; **may-taint union** на join (R227) |
| Forward CFG (R239) | Списки statements аналізуються **один раз** (без whole-list re-exec). Тіла циклів — локальний monotone fixpoint на back-edge. Handlers `try` об’єднують pre-try + throw points після statements. Неповний `match` додає no-match fallthrough. `else` циклу бачить normal-termination стан (з join нульової ітерації). |
| Clearing | Присвоєння з «чистого» виразу знімає taint на шляху; join зберігає taint, якщо будь-яке плече його тримає |

## Поза scope

Міжпроцедурний потік, field-sensitive ключі, точні exception/`break` edges,
alias імпортів поза dotted callee, повні comprehension CFG, точність
`*args`/`**kwargs`.

## Приклад

```python
from core.taint import analyze_function_taint

report = analyze_function_taint("def f(x):\n    eval(x)\n", function="f")
assert report.findings[0].source == "param:x"
assert report.findings[0].sink == "eval"
```

Тести: `tests/test_taint.py`, `tests/test_taint_r239.py`.
