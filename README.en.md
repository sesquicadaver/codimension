# Codimension

[![CI](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml/badge.svg)](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPL%20v3-green.svg)](LICENSE)

> **Language / Мова:** English | [Українська](README.md)

**Experimental Python IDE** with a text editor and a **control-flow diagram** that updates while you edit code. Fork version: **4.11.0**.

This is an **active fork** of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). The upstream project has been unmaintained for over 4 years; `pip install codimension` on PyPI is an outdated upstream release, not this repository.

## Current features

- Python file editing with a **synchronized flow diagram** (control flow)
- Import, class, and dependency diagrams; dead code (vulture), complexity (radon), pyflakes in the editor
- **Projects** (`.cdm3`): venv interpreter, `excludeFromAnalysis`, no auto-load of last project on startup
- **Parsers:** pure-Python `brief_ast` / `flow_ast` on Python 3.10+ (no cdmpyparser/cdmcfparser)
- **Bundled plugins** (`cdmplugins/`): Ruff, Ruff format, Mypy, Pytest, Coverage, Bandit, pip-audit, TODO panel, Git (MVP)
- **Debugger:** breakpoints, watchpoints (UI + sync), greenlet contexts
- **CI:** ruff, mypy, pytest (46 tests), pip-audit

## Limitations (honest)

- Not a production-ready IDE; focus is code analysis and visualization, not a VS Code / PyCharm replacement
- Git plugin is MVP (no stash/merge UI); PRs via `gh` CLI
- Environment-aware analysis (Docker / SSH / K8s) — **not implemented**; only local venv in project properties
- Long-term plans (overlay metrics, AI, modular core) — [ROADMAP.md](ROADMAP.md), not current state

## Requirements

- Python **3.10–3.13** (CI: 3.10, 3.11, 3.12, 3.13)
- **PyQt5**, Linux (primary platform); Windows / macOS — experimental

## Installation

Source only:

```bash
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -U pip
pip install -r requirements.txt
pip install -e .
codimension
```

Details: [doc/en/INSTALL.md](doc/en/INSTALL.md) (English) | [doc/INSTALL.md](doc/INSTALL.md) (Ukrainian).

## Development

```bash
pytest tests/ -v
ruff check codimension cdmplugins
ruff format --check codimension cdmplugins
mypy $(find codimension cdmplugins -name '*.py' ! -path '*/flowui/everything.py')
pip-audit -r requirements.txt
```

Layout: `codimension/` (IDE), `cdmplugins/` (plugins), `tests/`, `doc/`.

PR checklist — [CONTRIBUTING.en.md](CONTRIBUTING.en.md). Module/test matrix — [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md).

## Documentation

| | |
| --- | --- |
| [doc/BILINGUAL.md](doc/BILINGUAL.md) | Bilingual documentation policy |
| [doc/en/README.md](doc/en/README.md) | Documentation index (English) |
| [doc/uk/README.md](doc/uk/README.md) | Індекс документації (укр.) |
| [FORK.en.md](FORK.en.md) | Fork changes vs upstream |
| [ROADMAP.md](ROADMAP.md) | Long-term plan (not current version) |
| [TODO_FIXME.en.md](TODO_FIXME.en.md) | Known issues |
| [ChangeLog](ChangeLog) | Change history |

External (archive): [codimension.org](http://codimension.org) — not updated. Active MCP app: [CAN-MCP](https://github.com/sesquicadaver/CAN-MCP).

## License

GPL v3. Modified version — see [FORK.en.md](FORK.en.md), [doc/en/LICENSE_COMPLIANCE.md](doc/en/LICENSE_COMPLIANCE.md).
