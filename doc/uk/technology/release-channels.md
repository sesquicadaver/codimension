> **Мова / Language:** Українська | [English](../../technology/release-channels.md)

# Канали релізу та promotion (R171 / R181)

Codimension тримає **одну** лінію `master` (solo-fork). Канали — це метадані
та форма PEP 440 тега, **не** паралельні гілки `stable` / `develop`.

## Канали

| Канал | Зміст | Типовий тег | GitHub prerelease |
| ----- | ----- | ----------- | ----------------- |
| `dev` | Tip / експеримент | `vX.Y.Z.devN` | так |
| `beta` | Pre-release soak | `vX.Y.ZbN` / `vX.Y.ZrcN` | так |
| `stable` | Звичайна поставка | `vX.Y.Z` | ні |

Дефолти в [`cdmverspec.py`](../../../codimension/cdmverspec.py)
(`version`, `release_channel`). Override: `CDM_RELEASE_CHANNEL`.

Перевірка оновлень (`utils.update_check`): `stable` ховає prerelease;
`beta` / `dev` — показують.

## Драбина promotion (R181)

Лише вперед: **`dev` → `beta` → `stable`**.

```shell
# Dry-run
python scripts/promote_release_channel.py --from-channel dev --to beta

# Записати release_channel у cdmverspec.py
python scripts/promote_release_channel.py --to beta --apply

# Стрибок (явно)
python scripts/promote_release_channel.py --from-channel dev --to stable --allow-skip --apply
```

Після `--apply`:

1. Коміт `cdmverspec.py` (+ ChangeLog / docs за потреби).
2. Зелений CI на цьому коміті.
3. Annotated tag і `git push --tags`.
4. `.github/workflows/release.yml` перевіряє tag == `cdmverspec.version` **і**
   форму PEP 440 vs `release_channel` через
   `scripts/promote_release_channel.py --validate-tag`.

## Чого свідомо немає

- Немає довгоживучих гілок `stable` / `develop` / `release`.
- Немає тихого auto-promote на кожен merge у `master`.
- Немає окремої лінії пакування на канал (одна `version` за раз).
