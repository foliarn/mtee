# MTEE Remote

MTEE Remote is the optional, self-hosted server for [MTEE](../README.md). It keeps a copy of
each user's music library and change journal, and lets several MTEE desktops (and later a phone
app) sync with it. MTEE works without it.

This folder is a separate Python project with its own `pyproject.toml`, `uv.lock` and licence.
It reuses MTEE's Qt-free modules (`mtee.domain.metadata`, `mtee.services.metadata_reader`) and
never imports PySide6.

**Status:** the server runs in Docker (plan 124). This README covers installing and running it.

## Licence

MTEE Remote is licensed under the GNU Affero General Public License version 3 or later
(`AGPL-3.0-or-later`); see [LICENSE](LICENSE). The MTEE desktop application stays under
`GPL-3.0-or-later`.

## Requirements

- Docker with Compose v2 (`docker compose version` must work).
- A Linux host.
- A Linux user that owns the music files. The container runs as that user's ids, so it can
  read and write the library.

## Quick install with the admin program

On the server host (Linux, Docker Engine with the Compose plugin), as a normal user that may use
Docker:

    curl -fsSL https://raw.githubusercontent.com/foliarn/mtee-remote/main/install.sh | sh

The script installs the server source and `mtee-remote-admin`, a terminal program that asks the
settings, builds and starts the server, creates the admin account and adopts the music folder.
It then shows the state of the server and lets you change the settings, the accounts, the
devices, the libraries and the streaming settings, read the logs, and update the server. See
[admin/README.md](admin/README.md). The steps below do the same by hand.

## Install

1. Clone the repository on the server and go to the server folder:

       cd MTEE/server

2. Copy the example settings and fill them in:

       cp .env.example .env

3. Find the ids of the user that owns the music files. Put them in `UID` and `GID` in `.env`:

       id -u
       id -g

4. Create the data folder (`DATA_DIR`, `./data` by default). Docker does not create it with the
   right owner for you. Make sure the user with `UID` and `GID` owns it. If it is missing or not
   writable, the server does not start.

5. Build the image and start the server:

       docker compose build
       docker compose up -d

6. Check that the server answers:

       curl http://127.0.0.1:8080/health

   The answer is a short JSON status. The port is `PORT` from `.env`.

Build again after you change `UID` or `GID`, because they are set when the image is built.

## Create the admin

Run this once. It asks for a password:

    docker compose exec server mtee-remote create-admin --username NAME

`NAME` is the MTEE account name. Use the same name as `ADMIN_USER` in `.env`, so that the
library path below matches.

## Adopt the existing music folder

Adoption makes the existing folder a library of the server. The server scans the folder and
computes hashes. It does not copy or change any file in it.

1. Before you adopt, save a SHA-256 list of the music folder. Keep the list outside the folder.
   `MUSIC_DIR` must be set in your shell to the same path as in `.env`:

       find "$MUSIC_DIR" -type f -print0 | sort -z | xargs -0 sha256sum > ~/music-before.sha256

2. Adopt the folder as the library `music`:

       docker compose exec server mtee-remote adopt-root --user NAME --path /music/NAME --name music

   `NAME` is the same as in the admin step. The path is the folder inside the container.

3. The hashes are computed in the background. To see the progress, call
   `GET /api/v1/library/status` with a device token. Only `/health` and the sign-in route
   answer without a token.

## Reverse proxy

Only the API and the health check may reach the server from the internet. Put a reverse proxy in
front of it, and let the proxy forward only these two paths. This is the Caddy example. It
assumes that Caddy runs in a container on the `proxy` network (see the commented block in
`compose.yaml`):

    remote.example.com {
        @remote path /api/* /health
        handle @remote {
            reverse_proxy mtee-remote:8080
        }
        handle {
            respond 404
        }
    }

Set `TRUSTED_PROXIES` in `.env` to the address that the proxy has when it connects to the
container. Otherwise the server uses the wrong client addresses.

**Warning:** never publish the container port directly to the internet. Never put MTEE Remote
behind a catch-all rule, such as one that forwards every path to the server. Any path the proxy
forwards that is not `/api/*` or `/health` is a path the server does not expect.

## Other commands

Run them with `docker compose exec server mtee-remote ...`:

- `create-user --username NAME [--admin] [--quota-gb N]` creates an account.
- `reset-password --username NAME` sets a new password for an account.
- `scan --user NAME [--root NAME]` scans a user's library again. Run it after copying files onto the server by hand (scp): the server does not rescan on its own, unless `MTEE_REMOTE_SCAN_INTERVAL` (seconds) is set.

## Streaming

The server streams an item at a level: `original`, `lossless`, `320` or `128`. Every response
supports HTTP Range. A file that already fits the level is sent as it is, and nothing is upscaled.

- `GET /api/v1/items/{id}/stream?level=&codecs=`: with the device token. `codecs` is the list of
  codecs the client takes (`flac`, `alac`, `aac`, `opus`, `mp3`); empty means `flac`, `aac`, `opus`.
- `POST /api/v1/items/{id}/stream-url`: a signed path (`/api/v1/s/<token>`) for players that cannot
  send the token header. It lasts 6 hours by default (`ttl_seconds`, 60 to 86400). The token stops
  working when its device is revoked or its user is disabled. The secret is `DATA_DIR/stream-secret.bin`.
- `GET /api/v1/items/{id}/cover?size=s|m|l`: the album cover at 128, 512 or 1200 px.

The response headers `X-MTEE-Codec`, `X-MTEE-Sample-Rate`, `X-MTEE-Bit-Depth` and `X-MTEE-Bitrate`
give the delivered format (bitrate in bits per second).

Transcodes are kept in `DATA_DIR/cache/transcodes/` and covers in `DATA_DIR/cache/covers/`. The
cache is disposable: stop the server and delete `DATA_DIR/cache/`. The server never writes to the
music folder for streaming.

The server reads the streaming settings (`max_transcodes`, `cache_limit_gb`, `wav_to_flac`,
`lossless_cap`) when it starts. A changed setting applies after the next restart.

## Data and backups

Everything the server keeps in `DATA_DIR`:

- `mtee-remote.db`: the database.
- `db-backups/`: a copy of the database, made before each migration.
- `backups/`: database backups that you upload.
- `uploads/` and `trash/`: files the server is working on.

Inside each music folder, two hidden folders belong to the server:

- `.mtee-tmp`: unfinished uploads.
- `.mtee-trash`: the server trash.

To back up, copy `DATA_DIR` and the music folder. Stop the server first, so that the database is
not copied while it is being written:

    docker compose stop

## Upgrade

    git pull
    cd server
    docker compose build
    docker compose up -d

The database is copied before each migration, in `db-backups/`.

## Development

Run these from this folder (`server/`):

    uv sync
    uv run pytest
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright

The tests that create audio files need `ffmpeg`. If it is not on `PATH`, they use the one in the
repository's `vendor/ffmpeg/bin` (fetch it with `pwsh -File scripts/fetch_ffmpeg.ps1` from the
repository root), or the file named by `MTEE_REMOTE_FFMPEG`.

To start a server by hand:

    MTEE_REMOTE_DATA=./.data MTEE_REMOTE_MUSIC=./.music uv run mtee-remote serve --port 8080
