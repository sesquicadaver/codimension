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

Requires ``paramiko`` / ``keyring`` as **runtime** dependencies (installed by
``pip install -e .`` and ``codimension_ctl.sh install``, including ``--minimal``).
The extra ``.[ssh]`` is kept as a compatibility alias.

## Relation to R124

[`ssh-execution.md`](ssh-execution.md) covers **headless run** when the script
path already exists on the remote host. Open/Create + Save upload + IDE **Run**
on SSH-bound projects are implemented here; full remote IDE **debug** remains
deferred.

## Platforms

SFTP paths are treated as POSIX-style (typical for OpenSSH on Linux, macOS, and
Windows OpenSSH). Live Paramiko connectivity is best-effort; contract tests use
`FakeSftpSession` (no network).
