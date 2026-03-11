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
6. Upload to pypitest:

```shell
pip install twine
twine upload -r pypitest dist/*
```

7. Test from pypitest
8. Upload to PyPI:

```shell
twine upload dist/*
```

9. Create annotated tag:

```shell
git tag -a 4.10.0 -m "Release 4.10.0"
git push --tags
```

10. Publish release on GitHub (this fork): https://github.com/sesquicadaver/codimension/releases

## Development

```shell
pip install -e .
# or
python setup.py develop
```

## Links

- [Peter Downs — PyPI](http://peterdowns.com/posts/first-time-with-pypi.html)
- [Ewen Cheslack-Postava — packaging](https://ewencp.org/blog/a-brief-introduction-to-packaging-python/)
