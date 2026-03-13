# Contributing to Codimension (Fork)

Цей проєкт — форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Оригінал не підтримується.

## Як внести зміни

1. **Fork** репозиторій (якщо ще не зробили)
2. Створіть гілку: `git checkout -b feature/your-feature`
3. Внесіть зміни, дотримуючись існуючого стилю
4. Запустіть перевірки: `ruff check codimension cdmplugins`, `mypy $(find cdmplugins -name '*.py')`, `pytest tests/`
5. Оновіть ChangeLog
6. Зробіть commit з зрозумілим повідомленням
7. Push та створіть [Pull Request](https://github.com/sesquicadaver/codimension/compare) (шаблон заповниться автоматично)

**Issues:** при створенні issue оберіть шаблон (Bug report / Feature request).

## Стандарти

- **Код:** ruff (E, F, W, I), mypy
- **Документація:** оновлювати doc/, README, ChangeLog при зміні функціоналу
- **Ліцензія:** GPL v3. Зберігати copyright оригіналу у модифікованих файлах

## Середовище

Рекомендовано працювати у віртуальному середовищі (venv):

```shell
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

## CI

Перевірки запускаються автоматично при PR: ruff, mypy, pytest, pip-audit. Див. [Actions](https://github.com/sesquicadaver/codimension/actions).

## Документація

- [FORK.md](FORK.md) — статус форку
- [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md) — вимоги GPL
- [doc/github-integration-plan.md](doc/github-integration-plan.md) — план інтеграції з GitHub
- [TODO_FIXME.md](TODO_FIXME.md) — відомі проблеми
