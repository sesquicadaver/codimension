# Remote projects over SSH

Codimension can open and create projects whose **canonical tree lives on a
remote host**. The IDE keeps a **local cache** and treats the downloaded
`.cdm3` like a normal project.

Technology details: [SSH remote project](../technology/ssh-remote-project.md).
Headless remote run (no project bootstrap): [SSH ExecutionTarget](../technology/ssh-execution.md).

## Prerequisites

- Default install includes SSH extras (`paramiko`, `keyring`):
  `./scripts/codimension_ctl.sh install --yes`
- Or manually: `python -m pip install -e '.[ssh]'`
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
| **Save** | Uploads the file to the remote path (remote is source of truth) |
| **Run** | Uploads the script and runs `python3 <remote-script>` over SSH; output goes to Log / redirected IO |
| **Debug / Profile** | Refused with a clear message (full remote IDE debug is not implemented yet) |

## Auth and profiles

| Mode | Notes |
| ---- | ----- |
| SSH key / agent | Paramiko looks for keys/agent; optional identity file |
| Password | Optional store in OS keyring or `~/.codimension3/ssh_password_<id>` (mode `0600`) |

Host profiles (no secrets): `~/.codimension3/ssh_hosts.json`.

## Download size

By default the **entire** remote project tree is downloaded (no file/byte cap).
Optional safety stops: env `CDM_SSH_MAX_FILES` / `CDM_SSH_MAX_BYTES`, or API
kwargs (see technology doc). Skipped dirs include `.git`, `__pycache__`,
`.venv`, `venv`, `node_modules`.

## Tips

- Prefer a stable checkout path (not Trash). Desktop launchers refuse Trash
  checkouts; after moving the repo use `cd -P` so `$PWD` matches the real path.
- After `git pull` on the IDE checkout: `./scripts/codimension_ctl.sh install --yes`
  and fully restart the IDE so new menu items appear.
