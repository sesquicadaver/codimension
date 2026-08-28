# Installing Codimension (fork)

> **Language / Мова:** English | [Українська](../INSTALL.md)

**Active repository:** https://github.com/sesquicadaver/codimension  
**Version:** 4.11.0  

This fork is **not** published to the PyPI project named `codimension`. Install from a GitHub checkout. `pip install codimension` on PyPI is upstream 4.9.1 (2020).

## Recommended: deploy script

From the repository root:

```bash
./scripts/codimension_ctl.sh install --yes --desktop
# (safe from any cwd; install always uses the repo root)
./scripts/run_codimension.sh
```

| Command | Action |
| ------- | ------ |
| `install --yes` | `.venv` + editable install with tools/lint/test/security (paramiko/keyring are runtime) |
| `install --minimal --yes` | runtime dependencies only |
| `install --reinstall --yes` | wipe `.venv` and reinstall |
| `install --desktop --yes` | `~/.local/share/applications/` launcher → `scripts/run_codimension.sh` (refuse Trash checkouts) |
| `uninstall --yes` | remove `.venv` and local desktop launcher |
| `uninstall --purge-config --yes` | same + `~/.codimension3` |

Launch: `./scripts/run_codimension.sh`  
Help: `./scripts/codimension_ctl.sh --help`

After `git pull`: `./scripts/codimension_ctl.sh install --yes` (editable picks up code; use `--reinstall` if the venv is broken).

## Supported platforms

| Platform | Status |
| -------- | ------ |
| Linux | CI-tested (Ubuntu) |
| Windows | Unverified — no compatibility guarantee |
| macOS | Unverified — no compatibility guarantee |

## Python

- Verified in CI: **3.10, 3.11, 3.12, 3.13**
- Metadata `requires-python`: `>=3.10`

Optional: `PYTHON=/usr/bin/python3.12 ./scripts/codimension_ctl.sh install --yes`

## Manual install (without the script)

```bash
git clone https://github.com/sesquicadaver/codimension.git
cd codimension
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[tools,lint,test,security,ssh]"
./scripts/run_codimension.sh
```

On Python 3.11+, wrapt 1.12 (pylint stack) works via `codimension.inspect_compat`
(R197) — no separate `pip install wrapt --no-deps`.

Do not run the IDE from a checkout under **Trash** (the desktop launcher and
`run_codimension.sh` refuse that). After moving the repo: `cd -P /path/to/codimension`
so `$PWD` is not stuck on a deleted path.

## Removal

```bash
./scripts/codimension_ctl.sh uninstall --yes
./scripts/codimension_ctl.sh uninstall --purge-config --yes
```

## Next

- In-app user guide: [../user/index.md](../user/index.md)
- Remote SSH projects: [../user/ssh-remote-projects.md](../user/ssh-remote-projects.md)
- Repository: https://github.com/sesquicadaver/codimension
