> **Language / Мова:** [English](../../technology/k8s-execution.md) | Українська

# Kubernetes ExecutionTarget (R125)

Headless in-cluster запуски йдуть через
`utils.k8s_execution.KubernetesExecutionTarget`, який реалізує
`core.execution.ExecutionTarget`.

## Стратегія синхронізації (MVP)

- `ExecutionRequest.script` — шлях **в образі або volume**, уже доступний у поді.
- Автоматична збірка образу / sync ConfigMap у R125 відсутня.
- У metadata є `sync=in-image-or-volume-assumed`.
- Prepare-only результати також містять JSON Job stub (`job_stub`).

## Транспорт

| Транспорт | Роль |
| --------- | ---- |
| `FakeK8sJobTransport` | Контрактні тести / CI (без кластера) |
| `SubprocessKubectlTransport` | Best-effort `kubectl run` + logs |

## Неперевірені платформи

`SubprocessKubectlTransport` **не верифіковано** проти multi-tenant RBAC,
custom admission webhooks, Windows kubectl-обгорток і нестандартних CRD.
У CI віддавайте перевагу fake-транспорту; живий кластер перевіряйте перед
продакшеном.

## Режими

| Режим | Команда в поді (MVP) |
| ----- | -------------------- |
| run | `python script args…` |
| debug | `python -m pdb script…` |
| profile | `python -m cProfile -o outfile script…` |
