> **Language / Мова:** English | [Українська](../uk/technology/cfg-graph.md)

# CFG graph model (R140.a / R188)

Headless control-flow graphs live in `core.cfg` (`CfgNode` / `CfgEdge` /
`CfgGraph`). Flow UI binds them via `flowui.cfg_adapter`.

## Scopes and loops (R188)

- Each **function/class** gets nested `ENTRY` / `EXIT`. `return` / `raise` /
  `sys.exit` leave the **scope** exit, not only the module-global EXIT.
- **`break`** targets the innermost loop join; **`continue`** targets the
  loop header (`LOOP_BACK`).
- **`try`/`finally`**: terminals enter the finally node first; after the
  finally suite, edges also reach deferred targets (imprecise merge with the
  normal join path).

## Limits (not security-proof)

This CFG is a **structural navigation aid**, not a sound data-flow or
security analysis CFG. Exception edges, `with`/`async`, and finally merging
are approximate. Do not treat reachability here as a correctness or
vulnerability oracle.
