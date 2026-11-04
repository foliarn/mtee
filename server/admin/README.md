# mtee-remote-admin

A terminal interface to install, set up and run a [MTEE Remote](../README.md) server on a Linux
host with Docker.

## Install

On the server host (Linux, Docker Engine with the Compose plugin):

    curl -fsSL https://raw.githubusercontent.com/foliarn/mtee-remote/main/install.sh | sh

The script:

1. checks that `docker compose` works;
2. installs [uv](https://docs.astral.sh/uv/) in `~/.local/bin` if it is missing;
3. downloads the server source into `~/.local/share/mtee-remote/source`;
4. installs this program with `uv tool install`, as `~/.local/bin/mtee-remote-admin`;
5. starts it when the terminal allows.

It never asks for root, and it never writes outside your home folder. Run it again to install a
newer version of this program; the server source is replaced the same way as **Update** does.

Options, as environment variables in front of `sh`:

| Variable | Default | What it changes |
| --- | --- | --- |
| `MTEE_REMOTE_REPO` | `foliarn/mtee-remote` | The GitHub repository of the source. |
| `MTEE_REMOTE_REF` | `main` | The branch or tag to install. |
| `MTEE_REMOTE_HOME` | `~/.local/share/mtee-remote` | Where the source and the data go. |
| `MTEE_REMOTE_CONFIG` | `~/.config/mtee-remote` | Where the settings go. |
| `MTEE_REMOTE_TARBALL` | | A local `.tar.gz` of the source, instead of the download. |
| `MTEE_REMOTE_NO_START` | | Set to 1 not to start the interface at the end. |

For example: `curl -fsSL …/install.sh | MTEE_REMOTE_REF=v0.2.0 sh`.

## Use

    mtee-remote-admin            # the interface
    mtee-remote-admin --status   # one line, exit code 0 when the server runs and answers

The first run asks for the admin account, the music folder, the data folder, the port and the
address to listen on, and the admin password. It then builds the image, starts the server, creates
the admin account and adopts the music folder as its library.

The interface has these tabs:

- **Status**: the container, whether `/health` answers, the counts, hashing, and the libraries.
- **Settings**: every value of `server.env`, checked before it is saved. A change asks to restart
  the server (or to rebuild it, for the files owner `UID`/`GID`). A home-network address shows the
  plain-HTTP warning.
- **Users**: add, password (signs the devices out), quota, disable or enable, admin on or off,
  delete (the music folder is kept). The last active administrator cannot be removed.
- **Devices**: every device of every account; sign one out.
- **Libraries**: adopt a folder of the music volume, scan the libraries again.
- **Streaming**: transcodes at once, transcode cache, WAV as FLAC, lossless cap.
- **Logs**: the last 200 lines of the container.

Keys: `s` start, `x` stop, `r` restart, `u` update, `F5` read again, `q` quit.

## Where things are

- `~/.config/mtee-remote/server.env`: the settings, the `.env` that Docker Compose reads (mode 600).
- `~/.config/mtee-remote/admin.json`: the repository and branch the source comes from.
- `~/.local/share/mtee-remote/source/`: the server source; `source.previous/` is the one before the
  last update.
- `~/.local/share/mtee-remote/data/`: the default data folder (database, backups, uploads).

Compose runs as project `mtee-remote`:

    docker compose -p mtee-remote -f ~/.local/share/mtee-remote/source/server/compose.yaml \
      --env-file ~/.config/mtee-remote/server.env logs -f

## How it talks to the server

Through `docker compose exec -T server mtee-remote admin <command>`, which answers in JSON and
opens the server database directly: it works while the HTTP side is down, and no admin password
or token is kept on the host. A password goes to the command on stdin, never on its command line.

## Development

    uv sync
    uv run pytest
    uv run ruff check .
    uv run ruff format --check .
    uv run pyright

## Licence

AGPL-3.0-or-later, as the server. Textual is MIT.
