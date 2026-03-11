# Codimension Python 3 IDE

**Fork of [SergeySatskiy/codimension](https://github.com/SergeySatskiy/codimension).** Оригінальний проєкт не підтримується понад 4 роки. Цей форк — активна версія з підтримкою Python 3.11+.

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

**Потрібно:** Python 3.11+

Рекомендовано — у віртуальному середовищі:

```shell
python -m venv .venv
.venv/bin/pip install codimension
.venv/bin/codimension
```

Для діаграм залежностей потрібен graphviz:

```shell
sudo apt-get install graphviz
```

Для PlantUML — Java:

```shell
sudo apt-get install default-jre
```

## Розробка

```shell
# Клонувати цей форк (не оригінальний репозиторій)
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

.venv/bin/codimension
```

Додаткові можливості форку: `excludeFromAnalysis` (властивості проєкту), автоматичне виключення venv з аналізу.

## Ліцензія

GPL v3. Див. [LICENSE](LICENSE).

Модифікована версія — див. [FORK.md](FORK.md) та [doc/LICENSE_COMPLIANCE.md](doc/LICENSE_COMPLIANCE.md).

## Troubleshooting

Потрібні: g++, python3-dev, libpcre3-dev (Ubuntu):

```shell
sudo apt-get install g++ python3-dev libpcre3-dev
```
