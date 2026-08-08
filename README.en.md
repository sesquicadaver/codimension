# Codimension

> **Language / Мова:** English | [Українська](README.md)

[![CI](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml/badge.svg)](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPL%20v3-green.svg)](LICENSE)

**Experimental Python IDE** with a text editor and a **control-flow diagram** that updates while you edit. Fork version: **4.11.0**.

Active fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Last upstream `master` commit: **19 August 2022**. `pip install codimension` on PyPI is upstream **4.9.1** (2020), not this repository. This fork is **not** published to the PyPI project named `codimension`.

## What is verified today

- Python editing with a synchronized control-flow diagram
- Import / class / dependency diagrams; dead code, complexity, pyflakes in the editor
- `.cdm3` projects (no auto-load of the last project on startup)
- Local Project VENV (Tools → **VENV…** / **Update VENV…**; **Env:** status)
- Pure-Python AST parsers exposed under the compatibility names `cdmpyparser` / `cdmcfparser` (no C extension required)
- Plugin UI in `cdmplugins/` (Ruff, Mypy, Pytest, … need optional extras)
- Debugger (breakpoints, watchpoints); debugger session tests in CI
- CI on **Ubuntu**: Ruff, format, Mypy, pytest matrix **Python 3.10–3.13**, wheel + `pip check`, Qt offscreen bootstrap smoke, `pip-audit`

## Limitations

- Not a production-ready IDE
- **Linux** is the only CI-verified platform; Windows / macOS are **unverified** (no compatibility guarantee)
- Git plugin is MVP; PRs are created via the **GitHub REST API** (token: `gh auth` → OS keyring → `0600` file)
- Qt offscreen smoke in PR CI only constructs a bare `QApplication` (not MainWindow / plugins)
- Full MainWindow smoke is a weekly workflow, not a PR blocker
- Audit backlog closed in [TODO_FIXME.en.md](TODO_FIXME.en.md); active queue: [ROADMAP.md](ROADMAP.md) (first OPEN: R136)

## Requirements

- Python **3.10–3.13** (this is the CI matrix; versions beyond 3.13 are not verified here)
- PyQt5
- Linux (primary)

## Installation (end user)

```bash
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install .
codimension
```

Analyzer plugins (Ruff, Mypy, Pytest, …):

```bash
python -m pip install ".[tools,lint,test,security]"
```

Details: [doc/en/README.md](doc/en/README.md) → install ([doc/en/INSTALL.md](doc/en/INSTALL.md)).

## Development

```bash
python -m pip install -e ".[tools,lint,test,security]"
# or the convenience CI snapshot:
# python -m pip install -r requirements.txt && python -m pip install -e .
pytest tests/ -v
ruff check codimension cdmplugins
```

PR checklist: [CONTRIBUTING.en.md](CONTRIBUTING.en.md).

## Documentation

| | |
| --- | --- |
| [doc/en/README.md](doc/en/README.md) | English documentation index |
| [doc/uk/README.md](doc/uk/README.md) | Ukrainian documentation index |
| [doc/BILINGUAL.md](doc/BILINGUAL.md) | Bilingual documentation policy |
| [FORK.en.md](FORK.en.md) | Fork changes |
| [TODO_FIXME.en.md](TODO_FIXME.en.md) | Known issues (internal audit) |
| [ChangeLog](ChangeLog) | Change history |
| [doc/www/](doc/www/) | Local archive mirror of the old site |

## Related projects

- [CAN-MCP](https://github.com/sesquicadaver/CAN-MCP) — separate headless static-analysis MCP; **not** integrated into Codimension.

## License

GPL v3. See [FORK.en.md](FORK.en.md), [doc/en/LICENSE_COMPLIANCE.md](doc/en/LICENSE_COMPLIANCE.md).
