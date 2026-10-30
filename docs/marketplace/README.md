# MTEE Marketplace index

MTEE reads its plugin list from `index.json` in the default branch of the Marketplace
repository (`foliarn/mtee-plugins`). The address is `INDEX_URL` in
`src/mtee/plugins/marketplace.py`. This folder holds the starting file, with no plugins.

## Adding a plugin

1. Build the package with `scripts/pack_plugin.py`. The file is `<id>-<version>.mteeplugin`.
2. Create a GitHub release in the Marketplace repository, with a tag such as `spotify-0.2.0`,
   and upload the `.mteeplugin` file as a release asset.
3. Compute the SHA-256 (lowercase hex) and the size in bytes of the file, in PowerShell:

       (Get-FileHash -Algorithm SHA256 .\spotify-0.2.0.mteeplugin).Hash.ToLower()
       (Get-Item .\spotify-0.2.0.mteeplugin).Length

4. Add the entry to `index.json`, commit and push. The version `url` is the release asset address,
   `https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`. MTEE refuses any other
   address.

The `id`, `version`, `api_version`, `python` and `platform` values must match the package's
`plugin.json`. MTEE checks them after the download and refuses a mismatch.

## Example entry

```json
{
  "schema": 1,
  "plugins": [
    {
      "id": "spotify",
      "title": "Spotify",
      "description": "Plays and searches Spotify from MTEE.",
      "author": "Example Author",
      "homepage": "https://github.com/example/mtee-spotify",
      "licence": "GPL-3.0-or-later",
      "uses_network": true,
      "versions": [
        {
          "version": "0.2.0",
          "api_version": 1,
          "python": "3.12",
          "platform": "any",
          "url": "https://github.com/foliarn/mtee-plugins/releases/download/spotify-0.2.0/spotify-0.2.0.mteeplugin",
          "sha256": "3f1c9a0e7b2d4c6e8a10b5d7f9e1c3a5b7d9f0e2c4a6b8d0e1f3a5c7b9d2e4f6",
          "size": 2481930,
          "released": "2026-11-02"
        }
      ]
    }
  ]
}
```

A plugin can list several versions. MTEE offers the highest one it can install. A plugin whose
entry is malformed is skipped, and the others still appear.
