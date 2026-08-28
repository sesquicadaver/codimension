> **Language / Мова:** English | [Українська](../uk/technology/ssh-remote-project.md)

# SSH remote project open/create

Remote-first projects: the canonical tree lives on the SSH host; Codimension
keeps a **local cache** under `~/.codimension3/remote-projects/<profile-id>/`
and opens the downloaded `.cdm3` like a normal project.

## UI

- **Project → Open remote project (SSH)...** — connect, then **Browse…** in a
  remote file-manager dialog to pick a `.cdm3` or project directory; download
  and load the local cache.
- **Project → Create remote project (SSH)...** — connect, **Browse…** for the
  parent directory; same property fields as local New project (main script,
  markdown doc, remote venv/python, author, …) also via remote Browse…; create
  remote `.cdm3` + local cache.

Both items sit directly under local New/Open project. Use **Connect…** before
browsing (Browse will connect automatically if needed).


## Auth

| Mode | Behaviour |
| ---- | --------- |
| SSH key / agent | Paramiko `look_for_keys` / agent; optional identity file |
| Password | Paramiko password auth; optional remember via OS keyring or `ssh_password_<id>` mode `0600` |

Host profiles (no secrets) are stored in `~/.codimension3/ssh_hosts.json`.

## Path containment (R183)

- `profile.id` is a basename allowlist (`[A-Za-z0-9._-]`, max 80); path
  separators, absolute paths, `.` / `..` are rejected.
- Remote **project name** uses the same basename rules (max 128).
- Local cache paths are always under
  `<settings>/remote-projects/<id>/<digest>/`; `rmtree`/writes use
  `commonpath` checks and refuse escaping the cache container.

## Host authenticity (R184)

- Default policy is **reject** unknown host keys (no `AutoAddPolicy`).
- Codimension loads system/`~/.ssh/known_hosts` and optional
  `<settings>/ssh_known_hosts`.
- Profiles store `host_key_fingerprint` (`SHA256:…`). Mismatch → fail closed.
- First connection to an unknown host shows the fingerprint; TOFU only after
  explicit Yes, then the pin is saved with the profile.

## Download hardening (R185)

- Entries are classified with **`lstat`** (no symlink follow); remote
  symlinks are **rejected** (fail closed).
- File bodies are **streamed** in chunks (default 256 KiB), not fully buffered.
- Open downloads into a sibling **staging** directory, then **atomically
  renames** into the cache path so a failed sync keeps the previous tree.
- Default safety caps (override with kwargs / env; `0` = unlimited):

| Control | Default / meaning |
| ------- | ----------------- |
| `MAX_REMOTE_FILES` / `max_files` | 50 000 files |
| `MAX_REMOTE_BYTES` / `max_bytes` | 512 MiB |
| `CDM_SSH_MAX_FILES` | Env override for file count (when kwargs omitted) |
| `CDM_SSH_MAX_BYTES` | Env override for total bytes (when kwargs omitted) |

Skipped directory names: `.git`, `.hg`, `.svn`, `__pycache__`, `.venv`, `venv`,
`node_modules`.

## Edit / Run / Debug

When a project has `binding.json` in its local cache root:

- **Save** writes the local cache file, then schedules an **async SFTP upload**
  (R186). Local save success ≠ remote sync — sync state is
  `LOCAL` → `SYNCING` → `SYNCED` / `SYNC_FAILED` / `SYNC_CANCELLED`
  (`get_sync_state`). Uploads are cancelable and time-bounded
  (`CDM_SSH_TIMEOUT_SEC`, default 120s).
- **Run** schedules an **async** remote `python3 <script>` job (cancel,
  timeout, stdout/stderr capped at 2 MiB by default /
  `CDM_SSH_MAX_OUTPUT_BYTES`); output goes to the Log / redirected IO console.
- **Debug (R198)** uploads `client_cdm_dbg` under
  `<remote_root>/.codimension-dbg-client/`, opens a **reverse** port-forward
  (`remote 127.0.0.1:<port>` → local IDE `QTcpServer`), and runs the debuggee
  with `--host 127.0.0.1`. Protocol pathnames are remapped remote ↔ local
  cache (`utils.ssh_ide_debug`). Contract tests use `FakeReverseTunnel`
  (no network).
- **Profile** on SSH-bound projects is still refused (queued as **R199**).

Requires ``paramiko`` / ``keyring`` as **runtime** dependencies (installed by
``pip install -e .`` and ``codimension_ctl.sh install``, including ``--minimal``).
The extra ``.[ssh]`` is kept as a compatibility alias.

## Relation to R124

[`ssh-execution.md`](ssh-execution.md) covers **headless** run/debug when the
script path already exists on the remote host (`python -m pdb` for debug prep).
Open/Create + Save upload + IDE **Run** + IDE **Debug** (R198 reverse tunnel +
`client_cdm_dbg`) on SSH-bound projects are implemented here; IDE **Profile**
remains **R199**.

## Platforms

SFTP paths are treated as POSIX-style (typical for OpenSSH on Linux, macOS, and
Windows OpenSSH). Live Paramiko connectivity is best-effort; contract tests use
`FakeSftpSession` (no network).
