# Fork Status

Цей проєкт — **форк** [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).

## Чому форк

Оригінальний репозиторій не підтримується понад 4 роки. Сайт codimension.org та пов’язані репозиторії (cdm-pythonparser, cdm-flowparser) також не оновлюються.

**Клонувати або завантажувати з оригінального репозиторію немає сенсу** — використовуйте цей форк.

## Що змінено у форку

- Підтримка Python 3.11+
- Pure-Python fallback-парсери (`brief_ast`, `flow_ast`) коли C-розширення недоступні
- Сумісність з Python 3.12+ (imp, pkg_resources shims)
- `excludeFromAnalysis` — виключення шляхів з аналізу
- Автоматичне виключення venv з аналізу
- Lazy load для Classes/Functions/Globals
- Без автозавантаження останнього проєкту при старті
- Плагіни: Ruff, Mypy, Pytest, Coverage, Bandit, pip-audit, Ruff format, TODO panel

## Ліцензія

GPL v3. Збережено всі copyright-нотатки оригіналу. Див. [LICENSE](LICENSE) та [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md).

## Репозиторій

Активний форк: https://github.com/sesquicadaver/codimension
