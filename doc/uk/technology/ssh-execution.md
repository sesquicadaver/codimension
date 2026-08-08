> **Language / Мова:** [English](../../technology/ssh-execution.md) | Українська

# SSH ExecutionTarget (R124)

Віддалені headless-запуски йдуть через `utils.ssh_execution.SSHExecutionTarget`,
який реалізує протокол `core.execution.ExecutionTarget`.

## Стратегія синхронізації (MVP)

- `ExecutionRequest.script` — це **віддалений** шлях, який уже має існувати на
  хості (або бути доступним після вашої власної синхронізації).
- Автоматичний `scp` / `rsync` у R124 не виконується.
- У metadata завжди є `sync=remote-path-assumed`.

## Транспорт

| Транспорт | Роль |
| --------- | ---- |
| `FakeSSHTransport` | Контрактні тести / CI (без мережі) |
| `SubprocessSSHTransport` | Best-effort обгортка над клієнтом OpenSSH |

## Неперевірені платформи

`SubprocessSSHTransport` **не верифіковано** на Windows OpenSSH-обгортках,
нестандартних `ProxyJump` / `ControlMaster` і клієнтах, відмінних від OpenSSH.
У автотестах віддавайте перевагу мокованому транспорту; живий SSH перевіряйте
на кожному деплої перед продакшеном.

## Режими

| Режим | Віддалена команда (MVP) |
| ----- | ----------------------- |
| run | `python script args…` |
| debug | `python -m pdb script…` (без IDE TCP redirect) |
| profile | `python -m cProfile -o outfile script…` |
