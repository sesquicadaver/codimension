> **Language / Мова:** English | [Українська](../uk/technology/ssh-remote-project.md)

# SSH remote project open/create

Remote-first projects: the canonical tree lives on the SSH host; Codimension
keeps a **local cache** under `~/.codimension3/remote-projects/<profile-id>/`
and opens the downloaded `.cdm3` like a normal project.

## UI

- **Project → Open remote project (SSH)…** — connect, resolve remote `.cdm3`
  (file or directory containing one), download the project tree, load cache.
- **Project → New remote project (SSH)…** — create remote directory + `.cdm3`,
  seed the local cache, load it.

## Auth

| Mode | Behaviour |
| ---- | --------- |
| SSH key / agent | Paramiko `look_for_keys` / agent; optional identity file |
| Password | Paramiko password auth; optional remember via OS keyring or `ssh_password_<id>` mode `0600` |

Host profiles (no secrets) are stored in `~/.codimension3/ssh_hosts.json`.

## Download scope

By default the whole remote project tree is downloaded (**no** file-count or
byte-size cap). Optional safety stops:

| Control | Meaning |
| ------- | ------- |
| `max_files` / `max_bytes` kwargs | Positive integer = hard stop; `0` / omitted = unlimited |
| `CDM_SSH_MAX_FILES` | Env override for file count (when kwargs omitted) |
| `CDM_SSH_MAX_BYTES` | Env override for total bytes (when kwargs omitted) |

Skipped directory names: `.git`, `.hg`, `.svn`, `__pycache__`, `.venv`, `venv`,
`node_modules`.

## Edit / Run (no remote IDE debug yet)

When a project has `binding.json` in its local cache root:

- **Save** uploads the file to the remote path (source of truth = remote).
- **Run** uploads the script and executes `python3 <remote-script>` over SSH;
  stdout/stderr go to the Log / redirected IO console.
- **Debug / Profile** on SSH-bound projects are refused with a clear message
  (full remote IDE debug is deferred).

Requires `paramiko` (`pip install -e '.[ssh]'`; included in default
`codimension_ctl.sh install`).


## Dependency

Optional extra: `pip install -e '.[ssh]'` (pulls `paramiko` and `keyring`).

## Relation to R124

[`ssh-execution.md`](ssh-execution.md) covers **headless run** when the script
path already exists on the remote host. Open/Create here is the missing project
bootstrap; full remote-first edit/run/lint sync remains a follow-up.

## Platforms

SFTP paths are treated as POSIX-style (typical for OpenSSH on Linux, macOS, and
Windows OpenSSH). Live Paramiko connectivity is best-effort; contract tests use
`FakeSftpSession` (no network).
