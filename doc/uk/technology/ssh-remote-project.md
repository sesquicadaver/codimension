> **Language / Мова:** [English](../../technology/ssh-remote-project.md) | Українська

# Віддалений проєкт по SSH (open/create)

Remote-first: канонічне дерево на SSH-хості; Codimension тримає **локальний
кеш** у `~/.codimension3/remote-projects/<profile-id>/` і відкриває
завантажений `.cdm3` як звичайний проєкт.

## UI

- **Project → Open remote project (SSH)…** — підключення, пошук `.cdm3`,
  завантаження дерева, відкриття кешу.
- **Project → New remote project (SSH)…** — створення каталогу + `.cdm3` на
  хості, локальний кеш, відкриття.

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


## Залежність

Опційно: `pip install -e '.[ssh]'` (`paramiko`, `keyring`).

## Зв’язок з R124

[`ssh-execution.md`](ssh-execution.md) — headless run уже наявного remote-шляху.
Open/Create — bootstrap проєкту; повний remote-first edit/run/lint — наступні фази.
