# MTEE Remote server image (plan 124.8).
#
# Builds the self-hosted MTEE Remote server: Python 3.12, ffmpeg, and the `mtee` package
# from the repository root, running as a non-root user. The build context is the repository
# root, so run this from there:
#
#   docker build -f server/Dockerfile -t mtee-remote:local .
#
# (server/compose.yaml runs the same build.) The image is built locally and is never published.

FROM python:3.12-slim

# The container user's ids. Set them to the owner of the music files (`id -u`, `id -g`).
ARG UID=1000
ARG GID=1000

# The apt lists are removed in the same layer so they do not stay in the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# uv is pinned to the version used on the development machine.
COPY --from=ghcr.io/astral-sh/uv:0.12.12 /uv /bin/uv

# The `mtee` package is a path dependency (`mtee = { path = ".." }`), so the root project
# files must be present next to `server/`. Nothing else from the repository is copied.
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src/mtee/ ./src/mtee/
COPY server/ ./server/

WORKDIR /app/server
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN uv sync --locked --no-dev --no-editable
# The server must never import Qt: fail the build if PySide6 came in.
RUN /opt/venv/bin/python -c "import importlib.util, sys; sys.exit(importlib.util.find_spec('PySide6') is not None)"

RUN groupadd -g $GID mtee \
    && useradd -u $UID -g $GID -M -d /nonexistent -s /usr/sbin/nologin mtee \
    && mkdir -p /data /music \
    && chown mtee:mtee /data /music

USER mtee

ENV PATH=/opt/venv/bin:$PATH MTEE_REMOTE_DATA=/data MTEE_REMOTE_MUSIC=/music PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4)"

CMD ["mtee-remote", "serve", "--host", "0.0.0.0", "--port", "8080"]
