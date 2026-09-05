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

## Updater provenance (R215)

In-app update check / download / apply (`utils.update_check`,
`update_download`, `update_apply`, `update_provenance`):

| Rule | Behaviour |
| ---- | --------- |
| Releases API URL | HTTPS only; host `api.github.com`; path under `/repos/sesquicadaver/codimension/releases` (override via `CDM_UPDATE_OWNER_REPO`) |
| `CDM_UPDATE_RELEASES_URL` | Still subject to the same host/path policy (no arbitrary mirrors) |
| Extra hosts | `CDM_UPDATE_TRUSTED_HOSTS` (comma-separated) for API/download allowlist |
| Asset URLs | HTTPS on `github.com` / `objects.githubusercontent.com` / `release-assets.githubusercontent.com` |
| Size budgets | Releases JSON ≤ 2 MiB; checksum ≤ 64 KiB; artifact ≤ 256 MiB (`CDM_UPDATE_MAX_BYTES`) |
| Streaming | Production artifact download streams to disk; `ReleaseAsset.size` is a hard pre-check |
| Version probe | `importlib.metadata.version("codimension")` with `codimension.cdmverspec` fallback |

SHA-256 still proves integrity of bytes vs declared digest; provenance comes from
the trusted GitHub host/path policy above (digest alone is not enough if the
mirror is untrusted).

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
