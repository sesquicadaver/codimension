# Project Notes

**Fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).** Оригінал не підтримується. Активний форк: https://github.com/sesquicadaver/codimension

Розширені можливості: `excludeFromAnalysis`, venv auto-exclusion з аналізу.

---

# How to prepare a release

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
3. Edit `codimension/cdmverspec.py` setting the new version
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
8. **Автоматичний реліз (рекомендовано):** створіть тег — workflow `.github/workflows/release.yml` збудує та завантажить на PyPI:

```shell
git tag -a v4.10.0 -m "Release 4.10.0"
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
pip install -e .
# or
python setup.py develop
```

## Links

- [Peter Downs — PyPI](http://peterdowns.com/posts/first-time-with-pypi.html)
- [Ewen Cheslack-Postava — packaging](https://ewencp.org/blog/a-brief-introduction-to-packaging-python/)
