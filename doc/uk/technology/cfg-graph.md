> **Language / Мова:** [English](../../technology/cfg-graph.md) | Українська

# Модель CFG-графа (R140.a / R188)

Headless control-flow графи — у `core.cfg` (`CfgNode` / `CfgEdge` /
`CfgGraph`). Flow UI підключає їх через `flowui.cfg_adapter`.

## Scopes і цикли (R188)

- Кожна **function/class** має вкладені `ENTRY` / `EXIT`. `return` / `raise` /
  `sys.exit` виходять у **scope** exit, а не лише в module-global EXIT.
- **`break`** → join внутрішнього циклу; **`continue`** → заголовок циклу
  (`LOOP_BACK`).
- **`try`/`finally`**: термінали спочатку входять у finally; після suite також
  є ребра до відкладених цілей (неточне злиття з нормальним join).

## Обмеження (не security-proof)

Цей CFG — **структурна навігація**, не sound data-flow / security CFG.
Exception edges, `with`/`async` і злиття finally — наближені. Не трактуйте
reachability тут як оракул коректності чи вразливостей.
