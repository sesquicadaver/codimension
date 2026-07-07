# Contributing to Codimension (Fork)

> **Language / Мова:** English | [Українська](CONTRIBUTING.md)

This project is a fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Upstream is unmaintained.  
Active repository: https://github.com/sesquicadaver/codimension

## How to contribute

1. **Fork** the repository (if you have not already)
2. Create a branch: `git checkout -b feature/your-feature`
3. Make changes following existing style
4. Run checks (see CI section below)
5. Update `ChangeLog` and relevant docs in `doc/` (both languages when applicable — see [doc/BILINGUAL.md](doc/BILINGUAL.md))
6. Commit with a clear message
7. Push and open a [Pull Request](https://github.com/sesquicadaver/codimension/compare) (template fills automatically)

**Issues:** choose a template when creating an issue (Bug report / Feature request).

## Standards

- **Code:** ruff (E, F, W, I), mypy (`codimension` + `cdmplugins`)
- **Documentation:** update `doc/uk/`, `doc/en/`, canonical `doc/<topic>/`, `README.md`, `ChangeLog` when behavior changes
- **Living Specification:** when changing plugins or core modules — [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md)
- **License:** GPL v3. Keep original copyright in modified files
- **Anti-stub:** no `pass`/`return None` in production code without an explicit TODO; see [TODO_FIXME.en.md](TODO_FIXME.en.md)

## Environment

The project is tested only in a virtual environment (venv):

```shell
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

## CI (local, before PR)

```shell
. .venv/bin/activate
ruff check codimension cdmplugins
ruff format --check codimension cdmplugins
mypy $(find codimension cdmplugins -name '*.py' ! -path '*/flowui/everything.py')
pytest tests/ -v
pip-audit -r requirements.txt
```

Checks run automatically on PRs to `master`: [Actions](https://github.com/sesquicadaver/codimension/actions).

## Documentation

- [doc/BILINGUAL.md](doc/BILINGUAL.md) — bilingual policy
- [doc/en/README.md](doc/en/README.md) — full index (English)
- [doc/uk/README.md](doc/uk/README.md) — повний індекс (укр.)
- [FORK.en.md](FORK.en.md) — fork status
- [doc/en/INSTALL.md](doc/en/INSTALL.md) — installation
- [doc/en/LICENSE_COMPLIANCE.md](doc/en/LICENSE_COMPLIANCE.md) — GPL requirements
- [doc/en/github-integration-plan.md](doc/en/github-integration-plan.md) — CI, release, GitHub
- [doc/en/plugins/living-specification.md](doc/en/plugins/living-specification.md) — compliance matrix
- [TODO_FIXME.en.md](TODO_FIXME.en.md) — known issues
