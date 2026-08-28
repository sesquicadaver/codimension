> **Language / Мова:** English | [Українська](../uk/technology/release-channels.md)

# Release channels and promotion (R171 / R181)

Codimension uses a **single** `master` line (solo-fork). Channels are metadata
plus PEP 440 tag shape — **not** parallel `stable` / `develop` branches.

## Channels

| Channel | Meaning | Typical tag | GitHub prerelease |
| ------- | ------- | ----------- | ----------------- |
| `dev` | Tip / experimental | `vX.Y.Z.devN` | yes |
| `beta` | Pre-release soak | `vX.Y.ZbN` / `vX.Y.ZrcN` | yes |
| `stable` | Default shipping | `vX.Y.Z` | no |

Baked defaults live in [`cdmverspec.py`](../../codimension/cdmverspec.py)
(`version`, `release_channel`). Runtime override: `CDM_RELEASE_CHANNEL`.

Update checks (`utils.update_check`): `stable` hides GitHub prereleases;
`beta` / `dev` include them.

## Promotion ladder (R181)

Forward-only: **`dev` → `beta` → `stable`**.

```shell
# Dry-run
python scripts/promote_release_channel.py --from-channel dev --to beta

# Write release_channel into cdmverspec.py
python scripts/promote_release_channel.py --to beta --apply

# Jump (explicit)
python scripts/promote_release_channel.py --from-channel dev --to stable --allow-skip --apply
```

After `--apply`:

1. Commit `cdmverspec.py` (and ChangeLog / docs as needed).
2. Ensure CI is green on that commit.
3. Create and push the suggested annotated tag (`git tag -a …`).
4. `.github/workflows/release.yml` verifies tag == `cdmverspec.version` **and**
   tag PEP 440 shape matches `release_channel` via
   `scripts/promote_release_channel.py --validate-tag`.

## What we deliberately do not do

- No long-lived `stable` / `develop` / `release` git branches for this fork.
- No silent auto-promote on every merge to `master`.
- No second packaging line per channel (still one `version` string at a time).
