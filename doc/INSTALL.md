# Встановлення Codimension (форк)

> **Мова / Language:** Українська | [English](en/INSTALL.md)

**Активний репозиторій:** https://github.com/sesquicadaver/codimension  
**Версія:** 4.11.0  

Цей форк **не** опублікований у PyPI-проєкті `codimension`. Встановлюйте з GitHub checkout. `pip install codimension` на PyPI — upstream 4.9.1 (2020).

## Рекомендовано: скрипт розгортання

З кореня репозиторію:

```bash
./scripts/codimension_ctl.sh install --yes --desktop
# (safe from any cwd; install always uses the repo root)
./scripts/run_codimension.sh
```

| Команда | Дія |
| ------- | --- |
| `install --yes` | `.venv` + editable install з tools/lint/test/security |
| `install --minimal --yes` | лише runtime-залежності |
| `install --reinstall --yes` | знищити `.venv` і поставити заново |
| `install --desktop --yes` | ярлик у `~/.local/share/applications/` → `scripts/run_codimension.sh` (не з Trash) |
| `uninstall --yes` | видалити `.venv` і локальний desktop-ярлик |
| `uninstall --purge-config --yes` | те саме + `~/.codimension3` |

Запуск: `./scripts/run_codimension.sh`  
Довідка: `./scripts/codimension_ctl.sh --help`

Після `git pull`: `./scripts/codimension_ctl.sh install --yes` (editable підхопить код; `--reinstall` — якщо venv «зламаний»).

## Підтримувані платформи

| Платформа | Статус |
| --------- | ------ |
| Linux | CI-tested (Ubuntu) |
| Windows | Unverified — немає гарантій |
| macOS | Unverified — немає гарантій |

## Python

- Перевірено в CI: **3.10, 3.11, 3.12, 3.13**
- `requires-python`: `>=3.10`

Опційно: `PYTHON=/usr/bin/python3.12 ./scripts/codimension_ctl.sh install --yes`

## Ручне встановлення (без скрипта)

```bash
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[tools,lint,test,security]"
# Python 3.11+:
python -m pip install 'wrapt>=1.14' --no-deps
./scripts/run_codimension.sh
```

## Development / CI

```bash
./scripts/codimension_ctl.sh install --yes
# або:
python -m pip install -e ".[tools,lint,test,security]"
python -m pip install -r requirements.txt   # повний CI snapshot, не мінімум
```

## Видалення

```bash
./scripts/codimension_ctl.sh uninstall --yes
# повне очищення налаштувань IDE (recent projects тощо):
./scripts/codimension_ctl.sh uninstall --purge-config --yes
```

## Далі

- Користувацька довідка IDE: [user/index.md](user/index.md)
- Репозиторій: https://github.com/sesquicadaver/codimension
