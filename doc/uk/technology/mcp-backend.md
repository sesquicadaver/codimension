> **Мова / Language:** Українська | [English](../../technology/mcp-backend.md)

# MCP / remote agent backend (R182 / R214)

Codimension надає **headless** поверхню Model Context Protocol (MCP) над
існуючими core-API аналізу. IDE **не** залежить від MCP SDK.

## Встановлення

```shell
pip install 'codimension[mcp]'   # mcp>=2,<3
export CDM_MCP_TOKEN='your-secret'   # обовʼязково; fail-closed
export CDM_MCP_WORKSPACE='/path/to/project'   # або --workspace
codimension-mcp --workspace /path/to/project   # транспорт stdio
```

Пакет: `codimension/mcp_backend/` (назва свідома — щоб не затінювати PyPI-пакет
`mcp` у `sys.path`).

## Auth (fail-closed)

| Правило | Поведінка |
| ------- | --------- |
| Старт | Непорожній `CDM_MCP_TOKEN`; інакше код виходу `1` |
| Транспорт | Лише stdio в MVP — process-local trust після старту |
| Опційно на виклик | `hmac.compare_digest` у `mcp_backend.auth` |
| Немає SDK | Код виходу `2` з підказкою install |

Тихий старт без токена навмисно заборонений.

## Політика workspace (R214)

| Правило | Поведінка |
| ------- | --------- |
| Allowed root | Обовʼязково через `--workspace` або `CDM_MCP_WORKSPACE`; realpath; незмінний на час процесу |
| `open_workspace` | Лише каталоги під allowed root |
| Path tools | CFG / taint / фільтри файлів — під open root **і** allowed root |
| Бюджети | `CDM_MCP_MAX_FILES` (10000), `CDM_MCP_MAX_BYTES` (64 MiB), `CDM_MCP_MAX_DEPTH` (32); перевищення → `ResourceBudgetError` |
| Глибина | Шляхи глибше `max_depth` пропускаються (не помилка) |
| Модуль | `mcp_backend.policy.WorkspacePolicy` |

`0` для бюджету = без ліміту (небажано в production).

## MVP tools

| Tool | Headless backend |
| ---- | ---------------- |
| `open_workspace` | `utils.project_scan` + `utils.symbol_index_brief` (з бюджетами) |
| `list_project_files` | Список файлів сесії |
| `get_symbols` | `core.symbol_index` |
| `lookup_symbol` | `find_definitions` / `find_references` |
| `get_cfg` | `core.cfg.build_cfg_graph_from_file` |
| `explain_symbol` | `core.ai_context.build_ai_context` |
| `analyze_taint` | `core.taint` (heuristic; не security proof) |

## Поза MVP

- Повний клон CAN-MCP
- Qt / UI / plugins у MCP-процесі
- ExecutionTarget / SSH run
- Мережевий MCP HTTP listener

## Гейти

- Qt-free: `scripts/check_core_import_graph.py` включає `mcp_backend`
- Матриця шарів: `mcp_backend` → лише `core|infrastructure|app|utils`
- Тести: `tests/test_mcp_r182.py` (R182 auth + R214 policy)
