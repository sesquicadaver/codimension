# Детальна інструкція з встановлення Codimension

Codimension — мультиплатформна IDE. Підтримка платформ: **Linux** (основна), **Windows**, **macOS**.

## Системні вимоги

- **Python:** 3.10.12 або новіший (3.10–3.13)
- **ОС:** Linux, Windows 10/11, macOS 10.15+
- **Графіка:** Qt5 (PyQt5)

## Перевірка версії Python

**Linux / macOS:**

```shell
python3 --version
```

**Windows (CMD):**

```cmd
py -3 --version
```

або

```cmd
python --version
```

Потрібно: `Python 3.10.12` або вище.

---

## Шлях до pip та codimension

- **Linux, macOS:** `.venv/bin/pip`, `.venv/bin/codimension`
- **Windows:** `.venv\Scripts\pip.exe`, `.venv\Scripts\codimension.exe`

Далі в інструкції для Linux/macOS використовується `python3` та `.venv/bin/`. На Windows замініть на `py -3` (або `python`) та `.venv\Scripts\`.

---

## Варіант 1: Встановлення з PyPI (швидкий старт)

**Linux / macOS:**

```shell
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install codimension
.venv/bin/codimension
```

**Windows (CMD):**

```cmd
py -3 -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install codimension
.venv\Scripts\codimension
```

---

## Варіант 2: Встановлення з вихідного коду (розробка)

### Крок 1: Клонування репозиторію

```shell
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
```

### Крок 2: Системні залежності

#### Linux (Ubuntu / Debian / Fedora / Arch)

**Ubuntu / Debian:**

```shell
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip python3-dev
sudo apt-get install -y g++ libpcre3-dev
sudo apt-get install -y graphviz
```

**Fedora / RHEL:**

```shell
sudo dnf install python3 python3-pip python3-devel gcc-c++ graphviz
```

**Arch:**

```shell
sudo pacman -S python python-pip base-devel graphviz
```

- **graphviz** — для діаграм залежностей
- **g++/gcc, python3-dev** — для збірки (якщо потрібні)

PlantUML (опційно): `sudo apt-get install default-jre` (Ubuntu) або еквівалент.

#### Windows (системні пакети)

1. Встановіть [Python 3.10+](https://www.python.org/downloads/) (включіть "Add to PATH")
2. Встановіть [Graphviz](https://graphviz.org/download/) — додайте до PATH
3. Для збірки C-розширень: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (опційно)

#### macOS (Homebrew)

```shell
brew install python graphviz
```

Для збірки: Xcode Command Line Tools (`xcode-select --install`).

### Крок 3: Створення віртуального середовища

**Важливо:** `.venv` створюйте **локально на кожному комп'ютері**. Не копіюйте й не синхронізуйте `.venv` між машинами — у ньому зашиті абсолютні шляхи.

**Linux / macOS:**

```shell
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
```

**Windows:**

```cmd
py -3 -m venv .venv
.venv\Scripts\pip install --upgrade pip
```

### Крок 4–6: Залежності, встановлення, запуск

**Linux / macOS:**

```shell
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
.venv/bin/codimension
```

**Windows:**

```cmd
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
.venv\Scripts\codimension
```

---

## Повний скрипт встановлення

### Скрипт: Linux (Ubuntu/Debian)

```shell
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
sudo apt-get install -y python3 python3-venv python3-pip g++ python3-dev libpcre3-dev graphviz
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
.venv/bin/codimension
```

### Скрипт: Windows

```cmd
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
py -3 -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
.venv\Scripts\codimension
```

### Скрипт: macOS

```shell
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
brew install python graphviz
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
.venv/bin/codimension
```

---

## Оновлення з репозиторію

**Linux / macOS:**

```shell
cd codimension
git pull
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

**Windows:**

```cmd
cd codimension
git pull
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
```

---

## Troubleshooting

### Помилка: Python version outside allowed range

**Рішення:** Потрібен Python 3.10+. Перевірте версію (`python3 --version` / `py -3 --version`).

### Ubuntu 22.04: cdmpyparser / cdmcfparser

**Рішення:** На Python 3.10+ ці пакети не встановлюються — використовуються вбудовані fallbacks.

### `.venv` звертається до шляху іншого комп'ютера

**Рішення:** Видалити `.venv` і створити новий локально:

**Linux / macOS:**

```shell
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
```

**Windows:**

```cmd
rmdir /s /q .venv
py -3 -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
```

### externally-managed-environment

**Рішення:** Використовуйте venv. Не встановлюйте пакети в системний Python.

### Не відкриваються діаграми залежностей

**Рішення:** Встановіть graphviz і додайте до PATH (Linux: `apt install graphviz`, Windows: завантажте з graphviz.org, macOS: `brew install graphviz`).

### Помилка збірки (g++, python3-dev)

**Linux:** `sudo apt-get install g++ python3-dev libpcre3-dev`  
**macOS:** `xcode-select --install`  
**Windows:** Visual Studio Build Tools або встановлюйте лише wheel-пакети (без збірки).

---

## Структура після встановлення

```text
codimension/
├── .venv/           # Віртуальне середовище (не комітити в git)
├── codimension/     # Вихідний код IDE
├── cdmplugins/      # Плагіни (ruff, mypy, pytest тощо)
├── requirements.txt
├── pyproject.toml
└── setup.py
```

---

## Перевірка встановлення

**Linux / macOS:** `.venv/bin/codimension --help`  
**Windows:** `.venv\Scripts\codimension --help`

Або запустіть IDE і відкрийте `.py` файл — має з'явитися flow-діаграма справа.
