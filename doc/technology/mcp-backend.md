> **Language / Мова:** English | [Українська](../uk/technology/mcp-backend.md)

# MCP / remote agent backend (R182)

Codimension exposes a **headless** Model Context Protocol (MCP) surface over
existing core analysis APIs. The IDE itself does **not** depend on the MCP SDK.

## Install

```shell
pip install 'codimension[mcp]'   # pulls mcp>=2,<3
export CDM_MCP_TOKEN='your-secret'   # required; fail-closed
codimension-mcp                  # stdio transport
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

## MVP tools

| Tool | Headless backend |
| ---- | ---------------- |
| `open_workspace` | `utils.project_scan` + `utils.symbol_index_brief` |
| `list_project_files` | Session file list |
| `get_symbols` | `core.symbol_index` |
| `lookup_symbol` | `find_definitions` / `find_references` |
| `get_cfg` | `core.cfg.build_cfg_graph_from_file` |
| `explain_symbol` | `core.ai_context.build_ai_context` |
| `analyze_taint` | `core.taint` (heuristic; not a security proof) |

Paths must stay under the open workspace root.

## Out of scope (MVP)

- Full CAN-MCP tool clone
- Qt / UI / plugins inside the MCP process
- ExecutionTarget / SSH run
- Network MCP HTTP listener

## Gates

- Qt-free: `scripts/check_core_import_graph.py` includes `mcp_backend`
- Layer matrix: `mcp_backend` → `core|infrastructure|app|utils` only
- Tests: `tests/test_mcp_r182.py`
