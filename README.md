# Codimension Python 3 IDE

[![CI](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml/badge.svg)](https://github.com/sesquicadaver/codimension/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-GPL%20v3-green.svg)](LICENSE)

**Fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).** Оригінальний проєкт не підтримується понад 4 роки. Цей форк — активна версія з підтримкою Python 3.10+.

Експериментальна Python IDE з графічним аналізом коду (flow diagram, algorithmic tree).

## Посилання

- **Цей репозиторій** — активний форк для розробки та встановлення
- [Оригінальний проєкт (архів)](https://github.com/SergeySatskiy/codimension) — історичний, не підтримується
- [Технологія та візуалізація](http://codimension.org/documentation/visualization-technology/python-code-visualization.html)
- [Гарячі клавіші](http://codimension.org/documentation/cheatsheet.html)

**Примітка:** Сайт codimension.org та оригінальні репозиторії (cdm-pythonparser, cdm-flowparser) більше не оновлюються. Клонувати або завантажувати з upstream немає сенсу — використовуйте цей форк.

---

**Codimension** — вільна експериментальна Python IDE під ліцензією GPL v3.

Інтегрована система для:

- традиційного текстового редагування коду
- діаграмного аналізу коду (flow diagram, imports, classes тощо)

Головна особливість — автоматична генерація діаграми потоку керування під час набору коду. Ліва частина — текстовий редактор, права — діаграма, що оновлюється при паузі в наборі.

![Screenshot](doc/www/codimension.org/assets/cdm/images/habr/overview.png)

## Встановлення

**Потрібно:** Python 3.10+  
**Платформи:** Linux (основна), Windows, macOS

**Детальна інструкція:** [doc/INSTALL.md](doc/INSTALL.md)

### Швидкий старт (з PyPI) — Linux / macOS

```shell
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install codimension
.venv/bin/codimension
```

*Windows: використовуйте `py -3` та `.venv\Scripts\` — див. [doc/INSTALL.md](doc/INSTALL.md).*

### Розробка (з вихідного коду) — Linux / macOS

```shell
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
.venv/bin/codimension
```

*Windows та інші платформи — [doc/INSTALL.md](doc/INSTALL.md).*

Додаткові можливості форку: `excludeFromAnalysis` (властивості проєкту), автоматичне виключення venv з аналізу.

## Ліцензія

GPL v3. Див. [LICENSE](LICENSE).

Модифікована версія — див. [FORK.md](FORK.md) та [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md).

## Troubleshooting

Короткий список — повний опис у [doc/INSTALL.md](doc/INSTALL.md):

- **Системні пакети:** `sudo apt-get install g++ python3-dev libpcre3-dev graphviz`
- **Ubuntu 22.04:** Підтримується (Python 3.10)
- **`.venv` з іншого комп'ютера:** Видалити і створити новий локально (`rm -rf .venv` → `python3 -m venv .venv` → встановити залежності)
