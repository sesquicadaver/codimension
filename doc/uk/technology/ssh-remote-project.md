> **Language / Мова:** [English](../../technology/ssh-remote-project.md) | Українська

# Віддалений проєкт по SSH (open/create)

Remote-first: канонічне дерево на SSH-хості; Codimension тримає **локальний
кеш** у `~/.codimension3/remote-projects/<profile-id>/` і відкриває
завантажений `.cdm3` як звичайний проєкт.

## UI

- **Project → Open remote project (SSH)...** — Connect, потім **Browse…** у
  remote file-manager: вибір `.cdm3` або каталогу проєкту; завантаження кешу.
- **Project → Create remote project (SSH)...** — Connect, **Browse…** батьківського
  каталогу; поля як у локальному New project (main script, markdown, remote
  venv/python, author, …) теж через Browse…; створення remote `.cdm3` + кеш.

Обидва пункти — одразу під локальними New/Open. **Connect…** перед Browse
(або Browse підключить автоматично).


## Auth

| Режим | Поведінка |
| ----- | --------- |
| SSH key / agent | Paramiko keys/agent; опційний identity file |
| Password | Paramiko password; опційно keyring або `ssh_password_<id>` (0600) |

Профілі хостів (без секретів): `~/.codimension3/ssh_hosts.json`.

## Обсяг завантаження

За замовчуванням качається **все** дерево проєкту (**без** ліміту файлів/байтів).
Опційний захист диска:

| Керування | Значення |
| --------- | -------- |
| kwargs `max_files` / `max_bytes` | Додатне число = hard-stop; `0` / відсутнє = без ліміту |
| `CDM_SSH_MAX_FILES` | ENV для кількості файлів (якщо kwargs не задані) |
| `CDM_SSH_MAX_BYTES` | ENV для суми байтів (якщо kwargs не задані) |

Пропуск каталогів: `.git`, `.hg`, `.svn`, `__pycache__`, `.venv`, `venv`,
`node_modules`.

## Edit / Run (remote IDE debug ще немає)

Якщо в корені кешу є `binding.json`:

- **Save** — upload файлу на remote (джерело правди = remote).
- **Run** — upload скрипта + `python3 <remote-script>` по SSH; вивід у Log / IO.
- **Debug / Profile** для SSH-проєкту поки що відхиляються з повідомленням.

Потрібен `paramiko` (`pip install -e '.[ssh]'`; є в звичайному
`codimension_ctl.sh install`).


## Залежність

Опційно: `pip install -e '.[ssh]'` (`paramiko`, `keyring`).

## Зв’язок з R124

[`ssh-execution.md`](ssh-execution.md) — headless run уже наявного remote-шляху.
Open/Create — bootstrap проєкту; повний remote-first edit/run/lint — наступні фази.
