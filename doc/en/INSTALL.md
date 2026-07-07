> **Language / Мова:** English | [Українська](../INSTALL.md)

# Detailed Codimension Installation Guide

Codimension is a cross-platform IDE. Supported platforms: **Linux** (primary), **Windows**, **macOS**.

**Active fork:** https://github.com/sesquicadaver/codimension  
**Installation:** from source code in this repository only. The `pip install codimension` package on PyPI is an outdated version of the original project (2020), not this fork.

## System Requirements

- **Python:** 3.10.12 or newer (3.10–3.13)
- **OS:** Linux, Windows 10/11, macOS 10.15+
- **Graphics:** Qt5 (PyQt5)

## Checking Python Version

**Linux / macOS:**

```shell
python3 --version
```

**Windows (CMD):**

```cmd
py -3 --version
```

or

```cmd
python --version
```

Required: `Python 3.10.12` or higher.

---

## Paths to pip and codimension

- **Linux, macOS:** `.venv/bin/pip`, `.venv/bin/codimension`
- **Windows:** `.venv\Scripts\pip.exe`, `.venv\Scripts\codimension.exe`

The rest of this guide uses `python3` and `.venv/bin/` for Linux/macOS. On Windows, replace with `py -3` (or `python`) and `.venv\Scripts\`.

---

## Installation from Source

### Step 1: Clone the Repository

```shell
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
```

### Step 2: System Dependencies

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

- **graphviz** — for dependency diagrams
- **g++/gcc, python3-dev** — for building (if needed)

PlantUML (optional): `sudo apt-get install default-jre` (Ubuntu) or equivalent.

#### Windows (System Packages)

1. Install [Python 3.10+](https://www.python.org/downloads/) (include "Add to PATH")
2. Install [Graphviz](https://graphviz.org/download/) — add to PATH
3. For building C extensions: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (optional)

#### macOS (Homebrew)

```shell
brew install python graphviz
```

For building: Xcode Command Line Tools (`xcode-select --install`).

### Step 3: Create a Virtual Environment

**Important:** Create `.venv` **locally on each machine**. Do not copy or sync `.venv` between machines — it contains absolute paths.

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

### Steps 4–6: Dependencies, Installation, Launch

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

## Full Installation Scripts

### Script: Linux (Ubuntu/Debian)

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

### Script: Windows

```cmd
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
py -3 -m venv .venv
.venv\Scripts\pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
.venv\Scripts\codimension
```

### Script: macOS

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

## Updating from the Repository

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

## Developer Verification (Local CI)

```shell
. .venv/bin/activate
ruff check codimension cdmplugins
ruff format --check codimension cdmplugins
mypy $(find codimension cdmplugins -name '*.py' ! -path '*/flowui/everything.py')
pytest tests/ -v
pip-audit -r requirements.txt
```

---

## Troubleshooting

### Error: Python version outside allowed range

**Solution:** Python 3.10+ is required. Check the version (`python3 --version` / `py -3 --version`).

### Ubuntu 22.04: cdmpyparser / cdmcfparser

**Solution:** On Python 3.10+ these packages are not installed — built-in fallbacks are used instead (`brief_ast`, `flow_ast`).

### `.venv` points to another machine's path

**Solution:** Delete `.venv` and create a new one locally:

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

**Solution:** Use a venv. Do not install packages into system Python.

### Dependency diagrams do not open

**Solution:** Install graphviz and add it to PATH (Linux: `apt install graphviz`, Windows: download from graphviz.org, macOS: `brew install graphviz`).

### Build error (g++, python3-dev)

**Linux:** `sudo apt-get install g++ python3-dev libpcre3-dev`  
**macOS:** `xcode-select --install`  
**Windows:** Visual Studio Build Tools or install wheel packages only (no build).

### `pip install codimension` installs an old IDE

**Solution:** That is the original upstream package (Python 2 era). Clone the fork and install from source (see above).

---

## Directory Structure After Installation

```text
codimension/
├── .venv/           # Virtual environment (do not commit to git)
├── codimension/     # IDE source code
├── cdmplugins/      # Plugins (ruff, mypy, pytest, git, etc.)
├── tests/           # Unit tests (pytest)
├── requirements.txt
├── pyproject.toml
└── setup.py         # Legacy setuptools entry (main config — pyproject.toml)
```

---

## Verifying Installation

**Linux / macOS:** `.venv/bin/codimension --help`  
**Windows:** `.venv\Scripts\codimension --help`

Or launch the IDE and open a `.py` file — a flow diagram should appear on the right.
