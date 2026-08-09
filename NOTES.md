# Project Notes

> **Мова / Language:** Українська | [English](NOTES.en.md)

**Fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).** Оригінал не підтримується.  
**Активний форк:** https://github.com/sesquicadaver/codimension

## Встановлення для користувачів

Єдиний підтримуваний спосіб — клонування репозиторію та `pip install -e .` у venv.  
Див. [doc/INSTALL.md](doc/INSTALL.md).

`pip install codimension` з PyPI встановлює **застарілу upstream-версію (2020)**, не цей форк.

## Розширення форку

- `excludeFromAnalysis`, venv auto-exclusion з аналізу
- Generate requirements file; **VENV… / Update VENV…** (T140); status bar **Env:** (T141)
- Плагіни: ruff, mypy, pytest, coverage, bandit, pip-audit, git
- Debugger watchpoints, greenlet trace; offscreen e2e + nightly full-IDE smoke

---

# How to prepare a release (maintainers)

Реліз на PyPI **опційний** і не є основним способом доставки форку. Якщо потрібен тегований реліз:

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
   ``release_channel`` (``stable`` / ``beta`` / ``dev``; R171 — one version still).
   Publish a GitHub Release with a PEP 440 tag (``vX.Y.Z``) so Help → Check for
   updates (R172) can see it; download/apply remains R173+.
4. Build (recommended):

```shell
pip install build
python -m build
```

5. Verify `dist/` has required files
6. Upload to pypitest (опційно):

```shell
pip install twine
twine upload -r pypitest dist/*
```

7. Test from pypitest (якщо використовували крок 6)
8. **Автоматичний реліз:** створіть тег — workflow `.github/workflows/release.yml` збудує та завантажить на PyPI:

```shell
git tag -a v4.11.0 -m "Release 4.11.0"
git push --tags
```

Потрібен GitHub Secret `PYPI_API_TOKEN` (токен з pypi.org, формат pypi-xxx).

9. **Ручний upload:** якщо не використовуєте workflow:

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
