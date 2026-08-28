> **Language / Мова:** English | [Українська](NOTES.md)

# Project Notes

**Fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).** The original is unmaintained.  
**Active fork:** https://github.com/sesquicadaver/codimension

## Installation for Users

Recommended: `./scripts/codimension_ctl.sh install --yes --desktop`, then
`./scripts/run_codimension.sh` (see [doc/en/INSTALL.md](doc/en/INSTALL.md);
Ukrainian: [doc/INSTALL.md](doc/INSTALL.md)).
IDE Help: [doc/user/index.md](doc/user/index.md).

`pip install codimension` from PyPI installs the **outdated upstream version (2020)**, not this fork.

## Fork Extensions

- `excludeFromAnalysis`, venv auto-exclusion from analysis
- Generate requirements file; **VENV… / Update VENV…** (T140); status-bar **Env:** (T141)
- Plugins: ruff, mypy, pytest, coverage, bandit, pip-audit, git
- Debugger watchpoints, greenlet trace; offscreen e2e + nightly full-IDE smoke

## SSH remote projects (MVP)

**Project → Open remote project (SSH)...** / **Create remote project (SSH)...**
(directly under local New/Open). Connect + **Browse…** (remote file manager)
for dir/script/venv/docs — same fields as local New project.
Cache: `~/.codimension3/remote-projects/`. Save → upload; **Run** on host
(SSH debug deferred).
User guide: [doc/user/ssh-remote-projects.md](doc/user/ssh-remote-projects.md).
Technology: [doc/technology/ssh-remote-project.md](doc/technology/ssh-remote-project.md).

## AI (experimental)

**Options → Enable AI** / **AI settings…** / **AI actions**. Editor → **AI**.
Flag `ai_ui`; override `CDM_AI_UI=1`. Provider is user-chosen (OpenAI / Anthropic / Ollama) —
analysis requires a live provider (offline does not fake an LLM).
Base set: project analysis (all `.py`), module analysis **only in the open
project context** (local imports + neighbour modules), symbol analysis;
Google docstring + Apply (selection + lean support context to the model);
results in **AI Result** (Save); **AI Chat** is an on-demand panel.

## pylint / wrapt on Python 3.11+

`cdmpylintplugin` pulls `pylint==2.5.3` → `astroid==2.5` → `wrapt==1.12.1`
(pinned in `constraints.txt` so `pip install -c` resolves). Wrapt 1.12 imports
removed `inspect.formatargspec`. **R197:** `codimension.inspect_compat`
restores the API on `import codimension` / IDE startup — no
`pip install wrapt>=1.14 --no-deps` override.

---

# How to prepare a release (maintainers)

PyPI release is **optional** and is not the primary delivery method for the fork. If a tagged release is needed:

## Prepare the pypi config file `~/.pypirc`

```
[distutils]
index-servers =
  pypi
  pypitest

[pypi]
repository=https://pypi.python.org/pypi
username=<user>
password=<password>

[pypitest]
repository=https://test.pypi.org/legacy/
username=<user>
password=<password>
```

**Note:** Change permissions: `chmod 600 ~/.pypirc`

## Release Steps

1. Update ChangeLog
2. Make sure git clone is clean
3. Edit `codimension/cdmverspec.py` setting the new ``version`` and, if needed,
   ``release_channel`` (``stable`` / ``beta`` / ``dev``; R171 — still one version).
   Publish a GitHub Release with a PEP 440 tag (``vX.Y.Z``) and a wheel/sdist
   plus SHA-256 (API digest or ``*.sha256`` / ``SHA256SUMS``) so Help → Check for
   updates can verify a cache download (R172–R173); apply/install remains R180.
   Experimental AI UI: persistent flag ``ai_ui`` or env ``CDM_AI_UI`` (R174).
   Safe-mode IDE: ``codimension --safe-mode`` or ``CDM_SAFE_MODE=1`` (R175).
4. Build (recommended):

```shell
pip install build
python -m build
```

5. Verify `dist/` has required files
6. Upload to pypitest (optional):

```shell
pip install twine
twine upload -r pypitest dist/*
```

7. Test from pypitest (if step 6 was used)
8. **Automatic release:** create a tag — workflow `.github/workflows/release.yml` will build and upload to PyPI:

```shell
git tag -a v4.11.0 -m "Release 4.11.0"
git push --tags
```

Requires GitHub Secret `PYPI_API_TOKEN` (token from pypi.org, format pypi-xxx).

9. **Manual upload:** if not using the workflow:

```shell
twine upload dist/*
```

10. Publish release on GitHub: https://github.com/sesquicadaver/codimension/releases

## Development

```shell
pip install -r requirements.txt
pip install -e .
```

## Links

- [Peter Downs — PyPI](http://peterdowns.com/posts/first-time-with-pypi.html)
- [Ewen Cheslack-Postava — packaging](https://ewencp.org/blog/a-brief-introduction-to-packaging-python/)
