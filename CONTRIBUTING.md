# Contributing to Codimension (Fork)

> **Мова / Language:** Українська | [English](CONTRIBUTING.en.md)

Цей проєкт — форк [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension). Оригінал не підтримується.  
Активний репозиторій: https://github.com/sesquicadaver/codimension

## Політика гілок (R170)

- Єдина довгоживуча гілка: **`master`** (захищена: required `ci-gate`, без прямого push).
- Робочі гілки лише: **`feature/*`** (нова функціональність) або **`fix/*`** (виправлення).
- Зміни потрапляють у `master` **тільки через Pull Request** після зеленого CI.
- Не створюємо паралельних `stable` / `develop` / `release` гілок для цього форку.

## Як внести зміни

1. **Fork** репозиторій (якщо ще не зробили)
2. Створіть гілку від актуального `master`: `git checkout -b feature/your-feature` (або `fix/...`)
3. Внесіть зміни, дотримуючись існуючого стилю
4. Запустіть перевірки (див. розділ CI нижче)
5. Оновіть `ChangeLog` та відповідну документацію в `doc/`
6. Зробіть commit з зрозумілим повідомленням
7. Push та створіть [Pull Request](https://github.com/sesquicadaver/codimension/compare) у `master` (шаблон заповниться автоматично)

**Issues:** при створенні issue оберіть шаблон (Bug report / Feature request).

## Стандарти

- **Код:** ruff (E, F, W, I), mypy (`codimension` + `cdmplugins`)
- **Документація:** оновлювати `doc/uk/`, `doc/en/`, канонічні `doc/<topic>/`, `README.md`, `ChangeLog` при зміні функціоналу ([doc/BILINGUAL.md](doc/BILINGUAL.md))
- **Living Specification:** при зміні плагінів або core-модулів — [doc/plugins/living-specification.md](doc/plugins/living-specification.md)
- **Ліцензія:** GPL v3. Зберігати copyright оригіналу у модифікованих файлах
- **Anti-stub:** без `pass`/`return None` у production-коді без явного TODO; див. [TODO_FIXME.md](TODO_FIXME.md)

## Середовище

Проєкт тестується лише у віртуальному середовищі (venv):

```shell
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

## CI (локально перед PR)

```shell
. .venv/bin/activate
ruff check codimension cdmplugins
ruff format --check codimension cdmplugins
mypy $(find codimension cdmplugins -name '*.py' ! -path '*/flowui/everything.py')
pytest tests/ -v
pip-audit -r requirements.txt
```

Перевірки запускаються автоматично при PR на `master`: [Actions](https://github.com/sesquicadaver/codimension/actions).

## Документація

- [doc/BILINGUAL.md](doc/BILINGUAL.md) — двомовна документація
- [doc/README.md](doc/README.md) / [doc/en/README.md](doc/en/README.md) — індекси UK / EN
- [FORK.md](FORK.md) — статус форку
- [doc/INSTALL.md](doc/INSTALL.md) / [doc/en/INSTALL.md](doc/en/INSTALL.md) — встановлення
- [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md) — вимоги GPL
- [doc/github-integration-plan.md](doc/github-integration-plan.md) — CI, release, GitHub
- [doc/plugins/living-specification.md](doc/plugins/living-specification.md) — матриця відповідності
- [TODO_FIXME.md](TODO_FIXME.md) — відомі проблеми
