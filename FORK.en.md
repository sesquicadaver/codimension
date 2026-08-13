# Fork Status

> **Language / Мова:** English | [Українська](FORK.md)

This project is an **active fork** of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).

**Repository:** https://github.com/sesquicadaver/codimension  
**Version:** 4.11.0 (`codimension/cdmverspec.py`; `release_channel`, default `stable`)  
**Python:** 3.10+ (`pyproject.toml`: `requires-python >= "3.10"`)

## Why fork

The upstream repository has been unmaintained for over 4 years. The codimension.org site and related repos (cdm-pythonparser, cdm-flowparser) are also stale.

**There is no reason to clone or download from upstream** — use this fork.  
**Do not use `pip install codimension`** — PyPI has an outdated upstream package, not this fork.

## Changes in the fork

### Platform & parsers

- Python 3.10–3.13 support
- Pure-Python fallback parsers (`brief_ast`, `flow_ast`) instead of cdmpyparser/cdmcfparser C extensions
- Python 3.12+ compatibility (setuptools/distutils shims)

### Project analysis

- `excludeFromAnalysis` — exclude paths from analysis
- Automatic venv exclusion from analysis
- Lazy load for Classes/Functions/Globals
- Tools → Project utilities → Generate requirements file
- **Project VENV (T140/T141):** VENV… / Update VENV…; status-bar **Env:**; re-analyze; unresolved pip opt-in

### Plugins (`cdmplugins/`)

Ruff, Mypy, Pytest, Coverage, Bandit, pip-audit, Ruff format, TODO panel, **Git** (status, commit, push, pull, branch, Create/View PR via `gh`).

### Debugger & search

- Watchpoints: UI, edit dialog, remote sync with debuggee
- Greenlet `settrace` — greenlet context tracking in debugger
- Occurrences search redo (`searchAgain` / `canRedo`)
- Offscreen debugger e2e + nightly full-IDE smoke (T100–T130)

### Headless core / analysis (R100+)

- `ExecutionTarget`: local / Docker / SSH / Kubernetes MVP
- **SSH remote projects (UI):** Open/Create + SFTP Browse…; local cache;
  Save→upload; Run on host (IDE debug deferred). See
  [doc/user/ssh-remote-projects.md](doc/user/ssh-remote-projects.md)
- SymbolIndex, DependencyGraph, MetricProvider, OverlayLayer, risk score
- CFG model + taint MVP; AI: Options → AI + editor explain/suggest (`ai_ui` / `CDM_AI_UI`); provider+API key (default offline)
- Overlays: env / deps heat / deploy hints; update check + verified download (no auto-apply)
- Feature flags: `~/.codimension3/feature_flags.json`

### Other

- FS smart zoom (level 4) in flow UI
- mistune 3.x (`utils/md.py`), pip-audit without CVE ignore
- CI: ruff + mypy on `codimension` and `cdmplugins`, pytest matrix 3.10–3.13, wheel, offscreen GUI smoke, pip-audit (test counts — CI only)

### UX

- No auto-load of last project on startup (faster launch)

### Plan status

Linear R100+ queue **complete** (including R175 safe-mode). Deferred: R180–R182. See [ROADMAP.md](ROADMAP.md).

## Installation

Source only — see [README.en.md](README.en.md) and [doc/en/INSTALL.md](doc/en/INSTALL.md).

## License

GPL v3. All original copyright notices preserved. See [LICENSE](LICENSE) and [doc/en/LICENSE_COMPLIANCE.md](doc/en/LICENSE_COMPLIANCE.md).

## Documentation

- [doc/en/README.md](doc/en/README.md) — documentation index
- [ROADMAP.md](ROADMAP.md) — long-term plan
- [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md) — spec → module → tests matrix
- [TODO_FIXME.en.md](TODO_FIXME.en.md) — known issues
