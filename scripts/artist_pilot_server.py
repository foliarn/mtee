"""Local review tool; serves one private pilot directory, never the MTEE database."""

from __future__ import annotations

import argparse
import csv
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from artist_enrichment_pilot import ROLES, canonical_profile, now, read_json, write_json

STATIC = Path(__file__).parent / "artist-pilot-web"
DECISIONS = {"pending", "keep", "exclude", "uncertain"}


class ReviewStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.Lock()
        self.artists = read_json(directory / "artists.json")
        self.ids = {a["artist_id"] for a in self.artists}
        self.path = directory / "review.json"

    def reviews(self) -> dict:
        if self.path.exists():
            return read_json(self.path)
        result = {}
        csv_path = self.directory / "human-review.csv"
        if csv_path.exists():
            with csv_path.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    if row["artist_id"] in self.ids:
                        result[row["artist_id"]] = {
                            "decision": row["human_decision"],
                            "roles": row["roles_corrected"].split(";")
                            if row["roles_corrected"]
                            else None,
                            "notes": row["notes"],
                            "bass_related": None,
                        }
        return result

    def data(self) -> dict:
        with self.lock:
            result = {"artists": self.artists, "reviews": self.reviews()}
            for key, filename in {
                "tracks": "sample.json",
                "summary": "summary.json",
                "observations": "observations.json",
                "musicbrainz": "musicbrainz.json",
            }.items():
                result[key] = read_json(self.directory / filename)
            # The front has no use for private filesystem paths.
            result["tracks"] = [
                {k: v for k, v in t.items() if k != "path"} for t in result["tracks"]
            ]
            return result

    def save(self, artist_id: str, value: dict) -> dict:
        if artist_id not in self.ids:
            raise ValueError("Unknown artist")
        if value.get("decision") not in DECISIONS:
            raise ValueError("Invalid decision")
        roles = value.get("roles")
        if not isinstance(roles, list) or any(
            not isinstance(r, str) or r not in ROLES for r in roles
        ):
            raise ValueError("Invalid roles")
        if value.get("bass_related") is not None and type(value["bass_related"]) is not bool:
            raise ValueError("Invalid bass-related value")
        notes = value.get("notes", "")
        if not isinstance(notes, str) or len(notes) > 4000:
            raise ValueError("Notes limited to 4000 characters")
        identity = value.get("identity_decision", "pending")
        if identity not in {"pending", "accepted", "rejected"}:
            raise ValueError("Invalid identity review")
        profiles = {}
        for field, host in [
            ("spotify_url", "open.spotify.com"),
            ("soundcloud_url", "soundcloud.com"),
        ]:
            url = value.get(field, "")
            if not isinstance(url, str) or len(url) > 500:
                raise ValueError("Invalid profile")
            if url and (canonical_profile(url) is None or urlsplit(url).hostname != host):
                raise ValueError("Use a Spotify artist URL or SoundCloud profile URL")
            profiles[field] = canonical_profile(url) if url else ""
        record = {
            "decision": value["decision"],
            "roles": sorted(set(roles)),
            "bass_related": value.get("bass_related"),
            "notes": notes,
            "saved_at": now(),
            "identity_decision": identity,
            **profiles,
        }
        with self.lock:
            rows = self.reviews()
            rows[artist_id] = record
            write_json(self.path, rows)
        return record

    def export(self) -> bytes:
        with self.lock:
            reviews = self.reviews()
        observations = {o["artist_id"]: o for o in read_json(self.directory / "observations.json")}
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(
            [
                "artist_id",
                "artist",
                "interest_proposal",
                "roles_proposed",
                "human_decision",
                "roles_corrected",
                "bass_related_corrected",
                "notes",
                "identity_review",
                "spotify_url_corrected",
                "soundcloud_url_corrected",
            ]
        )
        for artist in self.artists:
            aid = artist["artist_id"]
            observation, review = observations.get(aid, {}), reviews.get(aid, {})
            values = [
                aid,
                artist["display_name"],
                observation.get("interest_proposal", "uncertain"),
                ";".join(observation.get("roles", [])),
                review.get("decision", "pending"),
                ";".join(review.get("roles") or []),
                review.get("bass_related"),
                review.get("notes", ""),
                review.get("identity_decision", "pending"),
                review.get("spotify_url", ""),
                review.get("soundcloud_url", ""),
            ]
            # Spreadsheet applications must not interpret user notes as formulas.
            writer.writerow(
                [
                    "'" + v
                    if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@"))
                    else v
                    for v in values
                ]
            )
        return ("\ufeff" + stream.getvalue()).encode("utf-8")


def make_server(directory: Path, port: int = 8765) -> ThreadingHTTPServer:
    store = ReviewStore(directory)

    class Handler(BaseHTTPRequestHandler):
        def send(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self) -> bool:
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected

        def do_GET(self) -> None:
            if not self.valid_host():
                self.send(403, b"Invalid host", "text/plain")
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/data":
                    self.send(
                        200,
                        json.dumps(store.data(), ensure_ascii=False).encode(),
                        "application/json; charset=utf-8",
                    )
                elif path == "/export.csv":
                    self.send(200, store.export(), "text/csv; charset=utf-8")
                elif path in {"/", "/app.js", "/style.css"}:
                    name = "index.html" if path == "/" else path[1:]
                    mime = {
                        "index.html": "text/html",
                        "app.js": "text/javascript",
                        "style.css": "text/css",
                    }[name]
                    self.send(200, (STATIC / name).read_bytes(), mime + "; charset=utf-8")
                else:
                    self.send(404, b"Not found", "text/plain")
            except (OSError, ValueError):
                self.send(500, b"Unable to read pilot files", "text/plain")

        def do_PUT(self) -> None:
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.valid_host() or self.headers.get("Origin") != origin:
                self.send(403, b"Invalid origin", "text/plain")
                return
            path = urlsplit(self.path).path
            if not path.startswith("/api/review/"):
                self.send(404, b"Not found", "text/plain")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 20000 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Invalid request")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                record = store.save(path.removeprefix("/api/review/"), payload)
                self.send(200, json.dumps(record).encode(), "application/json")
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, str(exc).encode(), "text/plain; charset=utf-8")
            except OSError:
                self.send(500, b"Unable to save; retry before leaving", "text/plain")

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = make_server(args.output, args.port)
    print(f"Review: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
