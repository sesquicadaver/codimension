> **Language / Мова:** [English](../../technology/cfg-graph.md) | Українська

# Модель CFG-графа (R140.a / R188 / R216)

Headless control-flow графи — у `core.cfg` (`CfgNode` / `CfgEdge` /
`CfgGraph`). Flow UI підключає їх через `flowui.cfg_adapter`.

## Scopes і цикли (R188)

- Кожна **function/class** має вкладені `ENTRY` / `EXIT`. `return` / `raise` /
  `sys.exit` виходять у **scope** exit, а не лише в module-global EXIT.
- **`break`** → join внутрішнього циклу; **`continue`** → заголовок циклу
  (`LOOP_BACK`).
- **`try`/`finally`**: термінали спочатку входять у finally; після suite також
  є ребра до відкладених цілей (неточне злиття з нормальним join).

## Loop else та match (R216)

- **Loop `else`:** за наявності `elsePart` нормальне виснаження циклу лише
  `loop → else [ELSE] → … → join`. **Немає** паралельного
  `loop → join [FALSE]` (обхід `else`). `break` як і раніше йде прямо в
  `join` через loop stack.
- **Невичерпний `match`:** якщо немає irrefutable catch-all (`case _:` або
  bare capture без `if` guard), додається `match → join [FALSE]`. Вичерпний
  match (наприклад хвостовий `case _:`) цього ребра не має.

## Обмеження (не security-proof)

Цей CFG — **структурна навігація**, не sound data-flow / security CFG.
Exception edges, `with`/`async` і злиття finally — наближені. Не трактуйте
reachability тут як оракул коректності чи вразливостей.
