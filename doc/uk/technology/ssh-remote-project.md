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

## Path containment (R183)

- `profile.id` — лише basename-allowlist (`[A-Za-z0-9._-]`, ≤80); separators,
  absolute paths, `.` / `..` відхиляються.
- Ім’я remote-проєкту — ті самі правила (≤128).
- Локальний кеш завжди під `<settings>/remote-projects/<id>/<digest>/`;
  `rmtree`/записи перевіряються через `commonpath`.

## Host authenticity (R184)

- За замовчуванням **reject** невідомих host keys (без `AutoAddPolicy`).
- Завантажуються system/`~/.ssh/known_hosts` і опційно
  `<settings>/ssh_known_hosts`.
- У профілі зберігається `host_key_fingerprint` (`SHA256:…`); mismatch → fail closed.
- Перше з’єднання з невідомим хостом показує fingerprint; TOFU лише після
  явного Yes, потім pin зберігається в профілі.

## Download hardening (R185)

- Класифікація через **`lstat`** (без follow symlink); remote symlink —
  **відхиляється** (fail closed).
- Тіла файлів **стрімляться** чанками (за замовчуванням 256 KiB).
- Open качає в sibling **staging**, потім **атомарно rename** у кеш — при
  помилці попереднє дерево зберігається.
- Дефолтні caps (override kwargs / env; `0` = без ліміту):

| Керування | За замовчуванням |
| --------- | ---------------- |
| `MAX_REMOTE_FILES` / `max_files` | 50 000 файлів |
| `MAX_REMOTE_BYTES` / `max_bytes` | 512 MiB |
| `CDM_SSH_MAX_FILES` | ENV для кількості файлів (якщо kwargs не задані) |
| `CDM_SSH_MAX_BYTES` | ENV для суми байтів (якщо kwargs не задані) |

Пропуск каталогів: `.git`, `.hg`, `.svn`, `__pycache__`, `.venv`, `venv`,
`node_modules`.

## Edit / Run / Debug

Якщо в корені кешу є `binding.json`:

- **Save** пише локальний кеш, потім планує **асинхронний SFTP upload** (R186).
  Успіх локального Save ≠ remote sync — стани
  `LOCAL` → `SYNCING` → `SYNCED` / `SYNC_FAILED` / `SYNC_CANCELLED`
  (`get_sync_state`). Upload скасовуваний і з timeout
  (`CDM_SSH_TIMEOUT_SEC`, дефолт 120с).
- **Run** — **асинхронний** remote `python3 <script>` (cancel, timeout,
  stdout/stderr ≤ 2 MiB / `CDM_SSH_MAX_OUTPUT_BYTES`); вивід у Log / IO.
- **Debug (R198)** — upload `client_cdm_dbg` у
  `<remote_root>/.codimension-dbg-client/`, **reverse** port-forward
  (`remote 127.0.0.1:<port>` → локальний IDE `QTcpServer`), запуск з
  `--host 127.0.0.1`. Шляхи протоколу remap remote ↔ local cache
  (`utils.ssh_ide_debug`). Контрактні тести — `FakeReverseTunnel`.
- **Profile (R199)** — **асинхронний** remote
  ``python3 -m cProfile -o <remote_root>/.codimension-profile/<id>.profile.out``
  (ті самі cancel/timeout/caps, що Run), потім **download** stats у локальний
  profile-output path і відкриття IDE profile report (якщо є main window).
  Контрактні тести мокають SFTP/`_exec_remote`.

Потрібні `paramiko` / `keyring` як **runtime**-залежності (`pip install -e .`
і `codimension_ctl.sh install`, включно з `--minimal`). Extra `.[ssh]`
залишено як сумісний аліас.


## Зв’язок з R124

[`ssh-execution.md`](ssh-execution.md) — headless run/debug/profile уже наявного
remote-шляху. Open/Create + Save + IDE **Run** + IDE **Debug** (R198) +
IDE **Profile** (R199) реалізовані тут.
