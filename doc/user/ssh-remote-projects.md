# Remote projects over SSH

Codimension can open and create projects whose **canonical tree lives on a
remote host**. The IDE keeps a **local cache** and treats the downloaded
`.cdm3` like a normal project.

Technology details: [SSH remote project](../technology/ssh-remote-project.md).
Headless remote run (no project bootstrap): [SSH ExecutionTarget](../technology/ssh-execution.md).

## Prerequisites

- Runtime install already includes `paramiko` and `keyring`
  (`./scripts/codimension_ctl.sh install --yes`, including `--minimal`)
- Network reachability to the host; key/agent or password auth

## Open an existing remote project

1. **Project → Open remote project (SSH)...**
2. Enter host, port, user; choose key or password; optional **Remember password**
3. **Connect…**, then **Browse…** and pick a remote `.cdm3` or project directory
4. Codimension downloads the tree into
   `~/.codimension3/remote-projects/<profile-id>/` and loads it

## Create a remote project

1. **Project → Create remote project (SSH)...**
2. Connect, then **Browse…** for the parent directory on the host
3. Fill the same property fields as local **New project** (name, main script,
   markdown doc, remote Python/venv, author, … — paths via remote Browse…)
4. Confirm: remote `.cdm3` is written and the local cache is opened

Both menu items sit directly under local **New project** / **Open project**.

## Edit and run

When the cache root contains `binding.json`:

| Action | Behaviour |
| ------ | --------- |
| **Save** | Writes locally, then **async** SFTP upload. Local save ≠ remote sync (`SYNCING`→`SYNCED`/`SYNC_FAILED`). Cancelable; timeout via `CDM_SSH_TIMEOUT_SEC` |
| **Run** | **Async** upload + `python3 <remote-script>` over SSH; cancel/timeout; output capped (`CDM_SSH_MAX_OUTPUT_BYTES`, default 2 MiB); output → Log / redirected IO |
| **Debug / Profile** | Refused with a clear message (full remote IDE debug is not implemented yet) |

## Auth and profiles

| Mode | Notes |
| ---- | ----- |
| SSH key / agent | Paramiko looks for keys/agent; optional identity file |
| Password | Optional store in OS keyring or `~/.codimension3/ssh_password_<id>` (mode `0600`) |

Host profiles (no secrets): `~/.codimension3/ssh_hosts.json`.

## Download size

Default safety caps: **50 000 files** / **512 MiB** (R185). Override with env
`CDM_SSH_MAX_FILES` / `CDM_SSH_MAX_BYTES`, or API kwargs (`0` = unlimited).
Remote **symlinks are refused**; download uses staging + atomic swap so a
failed sync keeps the previous local cache. Skipped dirs include `.git`,
`__pycache__`, `.venv`, `venv`, `node_modules`.

## Tips

- Prefer a stable checkout path (not Trash). Desktop launchers refuse Trash
  checkouts; after moving the repo use `cd -P` so `$PWD` matches the real path.
- After `git pull` on the IDE checkout: `./scripts/codimension_ctl.sh install --yes`
  and fully restart the IDE so new menu items appear.
