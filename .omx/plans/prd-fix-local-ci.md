# PRD: fix-local-ci

## Acceptance criteria
1. `ruff check codimension cdmplugins` — exit 0
2. `ruff format --check codimension cdmplugins` — exit 0
3. `mypy $(find cdmplugins -name '*.py')` — exit 0
4. `python -c "import codimension; import cdmplugins"` — OK
5. `pip-audit` — exit 0 (або documented ignore лише для mistune pin з коментарем у CI)
6. `pytest tests/ -v` — 15 passed

## Plan
1. `ruff check --fix` + `ruff format` на affected files
2. `githubapi._api_request`: `token: str | None`
3. Bump `pygments>=2.20.0`, `pytest>=9.0.3` у requirements.txt
4. Re-run pip-audit; для залишкових mistune CVE — `pip-audit` ignore у CI script або constraints file з обґрунтуванням
5. Full CI re-run + code-review
