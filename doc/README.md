# Документація Codimension (форк)

**Активний репозиторій:** https://github.com/sesquicadaver/codimension  
**Версія:** 4.11.0 | **Python:** 3.10+ | **Встановлення:** лише з вихідного коду ([INSTALL.md](INSTALL.md))

Цей індекс описує **актуальну** документацію форку. Каталог `doc/www/` — архівне дзеркало сайту codimension.org (2017–2020), не оновлюється.

---

## Швидкий старт

| Документ | Зміст |
| -------- | ----- |
| [../README.md](../README.md) | Огляд проєкту, встановлення, розробка |
| [INSTALL.md](INSTALL.md) | Детальна інструкція (Linux / Windows / macOS) |
| [../FORK.md](../FORK.md) | Що змінено відносно upstream |
| [../CONTRIBUTING.md](../CONTRIBUTING.md) | Як вносити зміни, CI |
| [../ROADMAP.md](../ROADMAP.md) | Довгостроковий план (Phase 0–38) |
| [../TODO_FIXME.md](../TODO_FIXME.md) | Відомі проблеми та anti-stub статус |
| [../ChangeLog](../ChangeLog) | Історія змін |

---

## Плагіни та CI

| Документ | Зміст |
| -------- | ----- |
| [plugins/plugins.md](plugins/plugins.md) | Туторіал з плагінів (англ.) |
| [plugins/plugins-implementation-plan.md](plugins/plugins-implementation-plan.md) | План фаз 0–5 (виконано) |
| [plugins/git-github-plugin-plan.md](plugins/git-github-plugin-plan.md) | Git/GitHub плагін (MVP реалізовано) |
| [plugins/living-specification.md](plugins/living-specification.md) | Матриця ТЗ → модуль → тести |
| [github-integration-plan.md](github-integration-plan.md) | CI, release, GitHub templates |
| [../NOTES.md](../NOTES.md) | Реліз на PyPI (для maintainers) |

---

## Функціональність IDE

| Документ | Зміст |
| -------- | ----- |
| [project/project.md](project/project.md) | Проєкти, властивості, venv, excludeFromAnalysis |
| [technology/technology.md](technology/technology.md) | Архітектура, парсери, flow UI |
| [md/mdsupport.md](md/mdsupport.md) | Markdown (mistune 3.x) |
| [smartzoom/smartzoom.md](smartzoom/smartzoom.md) | Smart zoom у flow diagram |
| [dependencies/dependencies.md](dependencies/dependencies.md) | Діаграма залежностей |
| [deadcode/deadcode.md](deadcode/deadcode.md) | Аналіз мертвого коду |
| [complexity/complexity.md](complexity/complexity.md) | Метрики складності |
| [disassembling/disassembling.md](disassembling/disassembling.md) | Дизасемблер |
| [colorschemes/colorschemes.md](colorschemes/colorschemes.md) | Кольорові схеми |
| [grouping/grouping.md](grouping/grouping.md) | Групування у діаграмах |
| [cml/cml.md](cml/cml.md) | CML doc comments |
| [pyflakes/pyflakes.md](pyflakes/pyflakes.md) | Pyflakes інтеграція |

---

## Ліцензія

| Документ | Зміст |
| -------- | ----- |
| [LICENSE_COMPLIANCE.md](LICENSE_COMPLIANCE.md) | GPL v3 для форку |
| [../FORK.md](../FORK.md) | Copyright та модифікації |

---

## Архів (не оновлюється)

- `doc/www/codimension.org/` — статичне дзеркало codimension.org
- Посилання на `pip install codimension`, Python 2, старі парсери — **не актуальні** для цього форку

---

## Оновлення документації

При зміні коду оновлюйте:

1. `ChangeLog`
2. Відповідний розділ у `doc/`
3. [plugins/living-specification.md](plugins/living-specification.md) — якщо змінились модулі або тести
4. [../TODO_FIXME.md](../TODO_FIXME.md) — якщо закрито або виявлено проблему
