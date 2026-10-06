"""Deterministic batches for an AI researching artists directly in a local chat."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from artist_enrichment_pilot import (
    MusicBrainzClient,
    canonical_profile,
    key,
    lucene_name,
    now,
    read_json,
    validate_observations,
    write_json,
)
from artist_enrichment_worker import SCHEMA, check_schema, musicbrainz_context


@contextmanager
def collection_lock(directory):
    stream = (directory / "automation.lock").open("a+b")
    try:
        if os.name == "nt":
            import msvcrt

            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        stream.close()


class ResearchSession:
    def __init__(self, store, client=None):
        self.store = store
        self.directory = store.directory
        self.path = self.directory / "research-session.json"
        self.client = client or MusicBrainzClient(self.directory / "musicbrainz-cache")

    def state(self):
        return (
            read_json(self.path)
            if self.path.exists()
            else {
                "active": None,
                "batches": {},
                "logs": [],
                "http_requests": 0,
                "cache_hits": 0,
                "status": "idle",
                "error": "",
            }
        )

    def inputs(self):
        with self.store.lock:
            reviews = self.store.reviews()
            observed = {o["artist_id"]: o for o in read_json(self.directory / "observations.json")}
        validated = {aid for aid, row in reviews.items() if row.get("validated_at")}
        pending = [
            a
            for a in self.store.artists
            if a["artist_id"] not in validated and a["artist_id"] not in observed
        ]
        return validated, observed, pending

    def status(self):
        state = self.state()
        validated, observed, pending = self.inputs()
        batch = state["batches"].get(state["active"], {})
        active = set(batch.get("artist_ids", [])) & {a["artist_id"] for a in pending}
        names = {a["artist_id"]: a["display_name"] for a in self.store.artists}
        return {
            "mode": "local-chat",
            "status": state["status"],
            "batch_id": state["active"],
            "current": [names[aid] for aid in batch.get("artist_ids", [])],
            "counts": {
                "queued": len(pending) - len(active),
                "running": len(active),
                "ready": len(set(observed) - validated),
                "validated": len(validated),
                "error": int(bool(state["error"])),
            },
            "logs": state["logs"],
            "error": state["error"],
            "http_requests": state["http_requests"],
            "cache_hits": state["cache_hits"],
        }

    def log(self, state, message):
        state["logs"] = (state["logs"] + [{"at": now(), "message": message[:600]}])[-100:]
        write_json(self.path, state)

    def next_batch(self, size=5):
        if type(size) is not int or not 1 <= size <= 10:
            raise ValueError("Lot : 1 à 10 artistes")
        with collection_lock(self.directory):
            state = self.state()
            validated, observed, pending = self.inputs()
            if state["active"]:
                active = state["batches"][state["active"]]
                if set(active["artist_ids"]) <= validated | set(observed):
                    active["status"] = "recovered"
                    state["active"] = None
                    self.log(state, "Lot déjà publié ou validé : checkpoint récupéré")
                else:
                    return read_json(self.directory / "research" / f"{state['active']}.json")
            if not pending:
                state.update(status="completed", error="")
                write_json(self.path, state)
                return {"batch_id": None, "artists": [], "status": "completed"}
            artists = pending[:size]
            local = {a["artist_id"]: [] for a in artists}
            sample_path = self.directory / "sample.json"
            for track in read_json(sample_path) if sample_path.exists() else []:
                for credit in track.get("credits", []):
                    context = local.get(credit["artist_id"])
                    if context is not None and len(context) < 6:
                        context.append(
                            {
                                "title": track.get("title", "")[:500],
                                "credits": [
                                    {
                                        "name": c.get("name", "")[:500],
                                        "role": c.get("credit_role", c.get("role", "")),
                                    }
                                    for c in track.get("credits", [])[:10]
                                ],
                            }
                        )
            bid = uuid.uuid4().hex
            packet = {
                "batch_id": bid,
                "artists": [
                    {
                        "artist_id": a["artist_id"],
                        "name": a["display_name"],
                        "titles": [t[:500] for t in a.get("representative_titles", [])[:6]],
                        "credit_roles": a.get("credit_roles", {}),
                        "collaborations": local[a["artist_id"]],
                    }
                    for a in artists
                ],
                "schema": SCHEMA,
            }
            folder = self.directory / "research"
            folder.mkdir(exist_ok=True)
            write_json(folder / f"{bid}.json", packet)
            state["batches"][bid] = {
                "artist_ids": [a["artist_id"] for a in artists],
                "status": "reserved",
                "created_at": now(),
            }
            state.update(active=bid, status="reserved", error="")
            self.log(state, f"Lot réservé : {len(artists)} artistes")
            return packet

    def collect_artist(self, artist):
        path = self.directory / "musicbrainz.json"
        checkpoint = read_json(path)
        aid = artist["artist_id"]
        previous = checkpoint.setdefault("artists", {}).get(aid, {})
        if previous.get("status") == "succeeded":
            return previous
        search = self.client.get("artist/", {"query": lucene_name(artist["name"]), "limit": 5})
        candidates = search.get("artists")
        if not isinstance(candidates, list):
            raise ValueError("Réponse MusicBrainz invalide")
        exact = [
            c
            for c in candidates
            if key(c.get("name", "")) == key(artist["name"])
            or any(key(a.get("name", "")) == key(artist["name"]) for a in c.get("aliases", []))
        ]
        details = []
        for candidate in exact[:2]:
            detail = self.client.get(
                "artist/" + candidate["id"], {"inc": "aliases+url-rels+genres+tags"}
            )
            detail["profile_links"] = [
                p
                for rel in detail.get("relations", [])
                if (p := canonical_profile(rel.get("url", {}).get("resource", "")))
            ]
            details.append(detail)
        result = {
            "status": "succeeded",
            "retrieved_at": now(),
            "candidates": candidates,
            "details": details,
            "identity_status": "needs_audit",
            "search_is_empty": not candidates,
        }
        checkpoint["artists"][aid] = result
        write_json(path, checkpoint)
        return result

    def collect(self):
        with collection_lock(self.directory):
            state = self.state()
            if not state["active"]:
                raise ValueError("Réserver un lot avec next avant collect")
            path = self.directory / "research" / f"{state['active']}.json"
            packet = read_json(path)
            state.update(status="musicbrainz", error="")
            before_requests, before_cache = self.client.requests, self.client.cache_hits
            try:
                for artist in packet["artists"]:
                    self.log(state, "MusicBrainz : " + artist["name"])
                    artist["musicbrainz"] = musicbrainz_context(self.collect_artist(artist))
                    write_json(path, packet)
                state["status"] = "audit"
                state["batches"][state["active"]]["collected"] = True
                self.log(state, "Collecte prête : recherche web dans la tâche locale")
                return packet
            except Exception as exc:
                state.update(status="paused", error=str(exc)[:600])
                self.log(state, "Collecte interrompue ; lot conservé pour reprise")
                raise
            finally:
                state["http_requests"] += self.client.requests - before_requests
                state["cache_hits"] += self.client.cache_hits - before_cache
                write_json(self.path, state)

    def import_result(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"batch_id", "observations"}:
            raise ValueError("Réponse attendue : batch_id + observations")
        check_schema({"observations": payload["observations"]}, SCHEMA)
        if not isinstance(payload["batch_id"], str):
            raise ValueError("Identifiant de lot invalide")
        with collection_lock(self.directory):
            state = self.state()
            batch = state["batches"].get(payload["batch_id"])
            if not batch:
                raise ValueError("Lot inconnu")
            rows = validate_observations(payload["observations"], self.store.artists)
            if set(rows) != set(batch["artist_ids"]):
                raise ValueError("Le résultat doit couvrir exactement les artistes du lot")
            for row in rows.values():
                if row["identity_status"] == "matched" and not row["sources"]:
                    raise ValueError("Identité confirmée sans source")
                if row["identity_status"] == "unresolved" and row["links"]:
                    raise ValueError("Ne pas attribuer de profil à une identité non résolue")
                for source in row["sources"]:
                    url = urlsplit(source["url"])
                    if not url.hostname or url.username or url.password:
                        raise ValueError("Source HTTPS invalide")
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if batch.get("digest") == digest:
                return {"imported": batch["imported"], "idempotent": True}
            if state["active"] != payload["batch_id"]:
                raise ValueError("Ce lot est déjà clos ; aucune réécriture autorisée")
            if not batch.get("collected"):
                raise ValueError("Terminer collect avant import")
            with self.store.lock:
                reviews = self.store.reviews()
                path = self.directory / "observations.json"
                existing = {o["artist_id"]: o for o in read_json(path)}
                imported = 0
                for aid, row in rows.items():
                    if not reviews.get(aid, {}).get("validated_at") and aid not in existing:
                        existing[aid] = row
                        imported += 1
                write_json(path, list(existing.values()))
            batch.update(status="published", imported=imported, digest=digest, finished_at=now())
            state.update(active=None, status="idle", error="")
            self.log(state, f"{imported} propositions publiées ; choix humains conservés")
            return {"imported": imported, "idempotent": False}

    def progress(self, message, *, paused=False):
        if not isinstance(message, str) or not 0 < len(message) <= 600:
            raise ValueError("Message : 1 à 600 caractères")
        with collection_lock(self.directory):
            state = self.state()
            if not state["active"]:
                raise ValueError("Aucun lot actif")
            if paused:
                state.update(status="paused", error=message)
            self.log(state, message)
        return self.status()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--database", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("next").add_argument("--size", type=int, default=5)
    commands.add_parser("collect")
    commands.add_parser("import").add_argument("--result", type=Path, required=True)
    commands.add_parser("progress").add_argument("--message", required=True)
    commands.add_parser("pause").add_argument("--message", default="Pause demandée")
    args = parser.parse_args()
    # Import here avoids a server/session circular dependency and starts no web server.
    from artist_pilot_server import ReviewStore

    session = ResearchSession(ReviewStore(args.output, args.database))
    if args.command == "status":
        result = session.status()
    elif args.command == "next":
        result = session.next_batch(args.size)
    elif args.command == "collect":
        result = session.collect()
    elif args.command == "import":
        if args.result.stat().st_size > 500_000:
            raise ValueError("Résultat limité à 500 Ko")
        result = session.import_result(read_json(args.result))
    else:
        result = session.progress(args.message, paused=args.command == "pause")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
