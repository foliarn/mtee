"""The sample plugin's track source: audio served over HTTP on 127.0.0.1, token required.

The server answers ``401`` to any request without ``Authorization: Bearer <TOKEN>``, so a test
that hears the track play has proved that the player sent the header. It keeps what it saw in
``requests``. It uses the standard library only and serves the bytes it was given (the tests
generate a short FLAC), with ``Range`` support because the player seeks with it.
"""

from __future__ import annotations

import contextlib
import http.server
import struct
import threading
import zlib
from dataclasses import dataclass

TOKEN = "sample-token"
SOURCE_KEY = "sample-url-track"
BROKEN_KEY = "sample-broken-track"


@dataclass(frozen=True, slots=True)
class Seen:
    """One request the server received: its method, its path and the header it carried."""

    method: str
    path: str
    authorization: str | None
    headers: dict[str, str]


class AudioServer:
    """A one-file HTTP server on a free port of the loopback interface, in a thread."""

    def __init__(self, audio: bytes, content_type: str = "audio/flac") -> None:
        self.requests: list[Seen] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                del format, args

            def do_HEAD(self) -> None:
                self._answer(send_body=False)

            def do_GET(self) -> None:
                self._answer(send_body=True)

            def _answer(self, *, send_body: bool) -> None:
                header = self.headers.get("Authorization")
                outer.requests.append(Seen(self.command, self.path, header, dict(self.headers)))
                if header != f"Bearer {TOKEN}":
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", "Bearer")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start, end = 0, len(audio) - 1
                status = 200
                requested = self.headers.get("Range", "")
                if requested.startswith("bytes="):
                    first, _, last = requested[6:].partition("-")
                    start = int(first) if first else 0
                    end = int(last) if last else end
                    end = min(end, len(audio) - 1)
                    status = 206 if start <= end else 416
                if status == 416:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{len(audio)}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = audio[start : end + 1]
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(len(body)))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(audio)}")
                self.end_headers()
                if send_body:
                    # The player may close the connection (a seek): nothing to report.
                    with contextlib.suppress(OSError):
                        self.wfile.write(body)

        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/track.flac"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def tiny_png() -> bytes:
    """Return a 1 x 1 PNG, the cover of the sample track, made without any image library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\x20\x80\x40")
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )
