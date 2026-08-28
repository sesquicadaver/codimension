> **Language / Мова:** English | [Українська](../uk/technology/k8s-execution.md)

# Kubernetes ExecutionTarget (R125)

Headless in-cluster runs go through
`utils.k8s_execution.KubernetesExecutionTarget`, implementing
`core.execution.ExecutionTarget`.

## Sync strategy (MVP)

- `ExecutionRequest.script` is an **in-image or volume** path already available
  inside the pod.
- No automatic image build / ConfigMap sync in R125.
- Metadata includes `sync=in-image-or-volume-assumed`.
- **R187:** `prepare_run` / `prepare_debug` / `prepare_profile` return an
  `ExecutionPlan` (argv + Job stub). `run` / `debug` / `profile` **execute**
  by default (not prepare-only).

## Transport

| Transport | Role |
| --------- | ---- |
| `FakeK8sJobTransport` | Contract tests / CI (no cluster) |
| `SubprocessKubectlTransport` | Best-effort `kubectl run` + terminal wait |

`SubprocessKubectlTransport` (R187 / A206): unique UUID pod names (not
`hash(argv)`); waits for phase **Succeeded/Failed** (not Ready); always
deletes the pod in `finally`.

## Unverified platforms

`SubprocessKubectlTransport` is **unverified** against multi-tenant RBAC,
custom admission webhooks, Windows kubectl wrappers, and non-Job CRDs. Prefer
the fake transport in CI; validate against your cluster before production use.

## Modes

| Mode | In-pod command (MVP) |
| ---- | -------------------- |
| run | `python script args…` |
| debug | `python -m pdb script…` |
| profile | `python -m cProfile -o outfile script…` |
