#!/bin/sh
# Install MTEE Remote's admin program and the server source, on a Linux host with Docker.
#
#   curl -fsSL https://raw.githubusercontent.com/foliarn/mtee-remote/main/install.sh | sh
#
# Writes only in your home folder, never asks for root:
#   ~/.local/share/mtee-remote/source   the server source (the one before: source.previous)
#   ~/.config/mtee-remote/admin.json    the repository and branch it came from
#   ~/.local/bin/mtee-remote-admin      the admin program, installed with `uv tool install`
# then starts mtee-remote-admin, which asks the settings and builds and starts the server.
#
# Options (environment variables, for example `curl ... | MTEE_REMOTE_REF=v0.2.0 sh`):
#   MTEE_REMOTE_REPO     GitHub repository of the source (default foliarn/mtee-remote)
#   MTEE_REMOTE_REF      branch or tag (default main)
#   MTEE_REMOTE_HOME     where the source and the data go (default ~/.local/share/mtee-remote)
#   MTEE_REMOTE_CONFIG   where the settings go (default ~/.config/mtee-remote)
#   MTEE_REMOTE_TARBALL  a local .tar.gz of the source instead of the download
#   MTEE_REMOTE_NO_START set to 1 not to start the admin program at the end
#   MTEE_REMOTE_SKIP_DOCKER_CHECK  set to 1 to install without Docker (tests only)

set -eu

REPO="${MTEE_REMOTE_REPO:-foliarn/mtee-remote}"
REF="${MTEE_REMOTE_REF:-main}"
HOME_DIR="${MTEE_REMOTE_HOME:-$HOME/.local/share/mtee-remote}"
CONFIG_DIR="${MTEE_REMOTE_CONFIG:-$HOME/.config/mtee-remote}"

say() { printf '%s\n' "$*"; }
fail() {
    printf 'mtee-remote install: %s\n' "$*" >&2
    exit 1
}

# The whole script is read before anything runs, so a download cut in the middle runs nothing.
main() {
    [ "$(uname -s)" = "Linux" ] || fail "MTEE Remote runs on a Linux host."
    if [ "$(id -u)" -eq 0 ]; then
        say "Note: you run this as root. A normal user that may use Docker is enough."
    fi
    case "$REPO" in
        */*) ;;
        *) fail "MTEE_REMOTE_REPO must be owner/name, got '$REPO'." ;;
    esac
    case "$REPO$REF" in
        *[!A-Za-z0-9._/-]*) fail "MTEE_REMOTE_REPO and MTEE_REMOTE_REF take letters, digits, '.', '_', '-' and '/' only." ;;
    esac
    for tool in curl tar; do
        command -v "$tool" >/dev/null 2>&1 || fail "'$tool' is required."
    done
    if [ "${MTEE_REMOTE_SKIP_DOCKER_CHECK:-}" != "1" ]; then
        command -v docker >/dev/null 2>&1 \
            || fail "Docker is required: https://docs.docker.com/engine/install/ (then run this again)."
        docker compose version >/dev/null 2>&1 \
            || fail "The Docker Compose plugin is required (\`docker compose version\` failed)."
    fi

    uv_bin="$(find_uv)"
    if [ -z "$uv_bin" ]; then
        say "Installing uv (https://docs.astral.sh/uv/) in ~/.local/bin..."
        curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh >/dev/null
        uv_bin="$(find_uv)"
        [ -n "$uv_bin" ] || fail "uv could not be installed."
    fi

    work="$(mktemp -d)"
    trap 'rm -rf "$work"' EXIT INT TERM
    if [ -n "${MTEE_REMOTE_TARBALL:-}" ]; then
        say "Using the source in $MTEE_REMOTE_TARBALL..."
        cp "$MTEE_REMOTE_TARBALL" "$work/source.tar.gz"
    else
        say "Downloading $REPO ($REF)..."
        curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$REF" -o "$work/source.tar.gz" \
            || fail "The source of $REPO ($REF) could not be downloaded."
    fi
    mkdir "$work/unpacked"
    tar -xzf "$work/source.tar.gz" -C "$work/unpacked" --no-same-owner \
        || fail "The source archive could not be unpacked."
    root="$work/unpacked"
    if [ ! -f "$root/server/compose.yaml" ]; then
        # A GitHub tarball holds one top folder: <name>-<ref>/.
        set -- "$work"/unpacked/*/
        [ "$#" -eq 1 ] && root="${1%/}"
    fi
    if [ ! -f "$root/server/compose.yaml" ] || [ ! -f "$root/server/admin/pyproject.toml" ]; then
        fail "The archive holds no MTEE Remote server (server/compose.yaml, server/admin)."
    fi

    mkdir -p "$HOME_DIR" "$CONFIG_DIR"
    rm -rf "$HOME_DIR/source.previous"
    if [ -d "$HOME_DIR/source" ]; then
        mv "$HOME_DIR/source" "$HOME_DIR/source.previous"
    fi
    mv "$root" "$HOME_DIR/source"
    printf '{\n  "repo": "%s",\n  "ref": "%s"\n}\n' "$REPO" "$REF" >"$CONFIG_DIR/admin.json"
    say "Server source in $HOME_DIR/source."

    say "Installing mtee-remote-admin..."
    "$uv_bin" tool install --force --quiet "$HOME_DIR/source/server/admin" \
        || fail "mtee-remote-admin could not be installed."
    bin_dir="$("$uv_bin" tool dir --bin)"
    admin="$bin_dir/mtee-remote-admin"
    [ -x "$admin" ] || fail "mtee-remote-admin is not in $bin_dir."
    say "Installed $admin."
    case ":$PATH:" in
        *":$bin_dir:"*) ;;
        *) say "Add $bin_dir to your PATH to run mtee-remote-admin by its name." ;;
    esac

    if [ "${MTEE_REMOTE_NO_START:-}" = "1" ]; then
        say "Run mtee-remote-admin to set up and start the server."
    elif (: </dev/tty) 2>/dev/null; then
        # stdin is the downloaded script: the interface reads the terminal instead.
        MTEE_REMOTE_HOME="$HOME_DIR" MTEE_REMOTE_CONFIG="$CONFIG_DIR" "$admin" </dev/tty
    else
        say "No terminal here: run mtee-remote-admin to set up and start the server."
    fi
}

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
    elif [ -x "$HOME/.local/bin/uv" ]; then
        printf '%s\n' "$HOME/.local/bin/uv"
    elif [ -x "${XDG_BIN_HOME:-}/uv" ]; then
        printf '%s\n' "$XDG_BIN_HOME/uv"
    fi
}

main "$@"
