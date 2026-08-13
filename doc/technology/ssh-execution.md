> **Language / Мова:** English | [Українська](../uk/technology/ssh-execution.md)

# SSH ExecutionTarget (R124)

Headless remote runs go through `utils.ssh_execution.SSHExecutionTarget`, which
implements the `core.execution.ExecutionTarget` protocol.

## Sync strategy (MVP)

- `ExecutionRequest.script` is a **remote** path that must already exist on the
  host (or be reachable after your own sync).
- No automatic `scp` / `rsync` is performed in R124.
- Metadata always includes `sync=remote-path-assumed`.

## Transport

| Transport | Role |
| --------- | ---- |
| `FakeSSHTransport` | Contract tests / CI (no network) |
| `SubprocessSSHTransport` | Best-effort OpenSSH client wrapper |

## Unverified platforms

`SubprocessSSHTransport` is **unverified** on Windows OpenSSH wrappers, custom
`ProxyJump` / `ControlMaster` layouts, and non-OpenSSH clients. Prefer mocked
transport in automated tests; validate live SSH per deployment before production use.

## Modes

| Mode | Remote command (MVP) |
| ---- | -------------------- |
| run | `python script args…` |
| debug | `python -m pdb script…` (no IDE TCP redirect) |
| profile | `python -m cProfile -o outfile script…` |

## Relation to SSH remote projects

IDE **Open/Create remote project**, Save→SFTP, and **Run on SSH** are documented
in [`ssh-remote-project.md`](ssh-remote-project.md) (user guide:
[Remote projects over SSH](../user/ssh-remote-projects.md)). R124 remains the
headless `ExecutionTarget` path when the remote script path already exists.
Full remote IDE debug is deferred.
