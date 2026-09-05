> **Language / Мова:** English | [Українська](../uk/technology/mcp-backend.md)

# MCP / remote agent backend (R182 / R214)

Codimension exposes a **headless** Model Context Protocol (MCP) surface over
existing core analysis APIs. The IDE itself does **not** depend on the MCP SDK.

## Install

```shell
pip install 'codimension[mcp]'   # pulls mcp>=2,<3
export CDM_MCP_TOKEN='your-secret'   # required; fail-closed
export CDM_MCP_WORKSPACE='/path/to/project'   # or pass --workspace
codimension-mcp --workspace /path/to/project   # stdio transport
```

Package layout: `codimension/mcp_backend/` (named so it does **not** shadow the
PyPI package `mcp` on `sys.path`).

## Auth (fail-closed)

| Rule | Behaviour |
| ---- | --------- |
| Startup | Non-empty `CDM_MCP_TOKEN` required; otherwise exit code `1` |
| Transport | Stdio only in MVP — process-local trust after startup |
| Optional per-call | `hmac.compare_digest` helpers in `mcp_backend.auth` |
| Missing SDK | Exit code `2` with install hint |

Silent open without a token is intentionally unsupported.

## Workspace policy (R214)

| Rule | Behaviour |
| ---- | --------- |
| Allowed root | Required via `--workspace` or `CDM_MCP_WORKSPACE`; realpath'd; immutable for the process |
| `open_workspace` | May only open directories under the allowed root |
| Path tools | CFG / taint / file filters resolve under open root **and** allowed root |
| Budgets | `CDM_MCP_MAX_FILES` (default 10000), `CDM_MCP_MAX_BYTES` (default 64 MiB), `CDM_MCP_MAX_DEPTH` (default 32); exceed → `ResourceBudgetError` |
| Depth | Paths deeper than `max_depth` are skipped (not an error) |
| Module | `mcp_backend.policy.WorkspacePolicy` |

`0` for a budget means unlimited (discouraged for production).

## MVP tools

| Tool | Headless backend |
| ---- | ---------------- |
| `open_workspace` | `utils.project_scan` + `utils.symbol_index_brief` (budgeted) |
| `list_project_files` | Session file list |
| `get_symbols` | `core.symbol_index` |
| `lookup_symbol` | `find_definitions` / `find_references` |
| `get_cfg` | `core.cfg.build_cfg_graph_from_file` |
| `explain_symbol` | `core.ai_context.build_ai_context` |
| `analyze_taint` | `core.taint` (heuristic; not a security proof) |

## Out of scope (MVP)

- Full CAN-MCP tool clone
- Qt / UI / plugins inside the MCP process
- ExecutionTarget / SSH run
- Network MCP HTTP listener

## Gates

- Qt-free: `scripts/check_core_import_graph.py` includes `mcp_backend`
- Layer matrix: `mcp_backend` → `core|infrastructure|app|utils` only
- Tests: `tests/test_mcp_r182.py` (R182 auth + R214 policy)
