"""Local review tool with optional validated enrichment persistence in the catalog DB."""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from artist_enrichment_pilot import ROLES, canonical_profile, motifs, now, read_json, write_json
from artist_research_session import ResearchSession
from artist_review_database import ReviewDatabase
from track_genre_audit import audit_track

STATIC = Path(__file__).parent / "artist-pilot-web"
DECISIONS = {"pending", "keep", "exclude", "uncertain"}


def has_correction(record: dict) -> bool:
    return bool(
        record.get("saved_at")
        or record.get("decision", "pending") != "pending"
        or record.get("notes")
        or record.get("roles") is not None
    )


class ReviewStore:
    def __init__(self, directory: Path, database: Path | None = None):
        self.directory = directory
        self.lock = threading.Lock()
        self.artists = read_json(directory / "artists.json")
        self.ids = {a["artist_id"] for a in self.artists}
        self.path = directory / "review.json"
        self.database = ReviewDatabase(database) if database else None

    def reviews(self) -> dict:
        result = {}
        if self.path.exists():
            result = read_json(self.path)
        csv_path = self.directory / "human-review.csv"
        if not self.path.exists() and csv_path.exists():
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
        if self.database:
            result.update(self.database.reviews())
        return result

    def data(self) -> dict:
        with self.lock:
            result = {"artists": self.artists, "reviews": self.effective_reviews()}
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
            rules_path = self.directory / "genre-rules.json"
            rules = read_json(rules_path) if rules_path.exists() else {}
            for track in result["tracks"]:
                track["genre_audit"] = audit_track(track, rules)
                if "credits" in track:
                    track["selection_categories"] = sorted(
                        set(track.get("selection_categories", [])) | motifs(track)
                    )
            return result

    def effective_reviews(self) -> dict:
        """Accept unchanged proposals; retain provenance and unresolved identities."""
        observations = {o["artist_id"]: o for o in read_json(self.directory / "observations.json")}
        saved = self.reviews()
        result = {}
        for aid in self.ids:
            o, r = observations.get(aid, {}), saved.get(aid, {})
            links = o.get("links", [])
            roles = list(o.get("roles", []))
            if "Producer" in roles and "DJ" not in roles:
                roles.append("DJ")
            record = {
                "decision": "exclude" if o.get("interest_proposal") == "exclude" else "keep",
                "roles": roles,
                "bass_related": o.get("bass_related") is True,
                "notes": "",
                "identity_decision": "pending"
                if o.get("identity_status") not in {"matched", "provisional"}
                else "accepted",
                "spotify_url": next(
                    (link["url"] for link in links if "open.spotify.com/artist/" in link["url"]), ""
                ),
                "soundcloud_url": next(
                    (link["url"] for link in links if "soundcloud.com/" in link["url"]), ""
                ),
                "accepted_by_default": True,
            }
            if has_correction(r):
                proposed_decision = record["decision"]
                record.update(
                    r if r.get("saved_at") else {k: v for k, v in r.items() if v is not None}
                )
                if record["decision"] == "pending":
                    record["decision"] = proposed_decision
                record["accepted_by_default"] = False
            record["tags"] = ["idgaf"] if record["decision"] == "exclude" else []
            result[aid] = record
        return result

    def validate(self, artist_id: str, value: dict) -> dict:
        if artist_id not in self.ids:
            raise ValueError("Unknown artist")
        if not isinstance(value, dict):
            raise ValueError("Expected an artist correction")
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
            "tags": ["idgaf"] if value["decision"] == "exclude" else [],
        }
        return record

    def save_many(self, changes: dict, *, validated: bool = False) -> dict:
        if not isinstance(changes, dict) or not changes or len(changes) > len(self.ids):
            raise ValueError("Expected known artist corrections")
        # Validate the entire batch before one atomic write; never save half a batch.
        records = {aid: self.validate(aid, value) for aid, value in changes.items()}
        if validated or self.database:
            for record in records.values():
                record["validated_at"] = now()
        with self.lock:
            if self.database:
                observations = {
                    o["artist_id"]: o for o in read_json(self.directory / "observations.json")
                }
                self.database.save(records, observations)
                return records
            rows = {aid: record for aid, record in self.reviews().items() if has_correction(record)}
            for aid, record in records.items():
                if "validated_at" not in record and rows.get(aid, {}).get("validated_at"):
                    record["validated_at"] = rows[aid]["validated_at"]
            rows.update(records)
            write_json(self.path, rows)
        return records

    def save(self, artist_id: str, value: dict) -> dict:
        return self.save_many({artist_id: value})[artist_id]

    def save_page(self, changes: dict) -> dict:
        if not isinstance(changes, dict) or not 0 < len(changes) <= 100:
            raise ValueError("A page contains 1 to 100 artists")
        return self.save_many(changes, validated=True)

    def export(self) -> bytes:
        with self.lock:
            reviews = self.effective_reviews()
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
                "acceptance",
                "artist_tags",
                "validation_state",
                "validated_at",
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
                "default" if review.get("accepted_by_default") else "correction",
                ";".join(review.get("tags", [])),
                "validated" if review.get("validated_at") else "pending",
                review.get("validated_at", ""),
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


def make_server(
    directory: Path, port: int = 8765, database: Path | None = None
) -> ThreadingHTTPServer:
    store = ReviewStore(directory, database)
    session = ResearchSession(store)

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
                if path == "/api/automation":
                    self.send(200, json.dumps(session.status()).encode(), "application/json")
                elif path == "/api/data":
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
            except (OSError, ValueError, sqlite3.Error):
                self.send(500, b"Unable to read pilot files", "text/plain")

        def do_PUT(self) -> None:
            origin = f"http://127.0.0.1:{self.server.server_port}"
            if not self.valid_host() or self.headers.get("Origin") != origin:
                self.send(403, b"Invalid origin", "text/plain")
                return
            path = urlsplit(self.path).path
            if path not in {"/api/reviews", "/api/page", "/api/automation"} and not path.startswith(
                "/api/review/"
            ):
                self.send(404, b"Not found", "text/plain")
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                limit = 16_000_000 if path in {"/api/reviews", "/api/page"} else 20000
                if not 0 < size <= limit or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Invalid request")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                if path == "/api/automation":
                    raise ValueError(
                        "Pilotage depuis la tâche locale ; worker automatique désactivé"
                    )
                elif path == "/api/page":
                    record = store.save_page(payload)
                elif path == "/api/reviews":
                    record = store.save_many(payload)
                else:
                    record = store.save(path.removeprefix("/api/review/"), payload)
                self.send(200, json.dumps(record).encode(), "application/json")
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, str(exc).encode(), "text/plain; charset=utf-8")
            except (OSError, sqlite3.Error):
                self.send(500, b"Unable to save; retry before leaving", "text/plain")

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--database", type=Path)
    args = parser.parse_args()
    server = make_server(args.output, args.port, args.database)
    print(f"Review: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
