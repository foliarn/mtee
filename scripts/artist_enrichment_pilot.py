"""Read-only artist enrichment experiment, independent of the MTEE application.

Personal snapshots, provider responses and review decisions belong in an ignored
directory. MusicBrainz returns candidates; neither search scores nor local credits
confirm a remote identity or a person's interest in an artist.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sqlite3
import time
import unicodedata
from collections import Counter
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

VERSION = "105.1"
USER_AGENT = "MTEEArtistPilot/105.1 (https://github.com/foliarn/mtee)"
MB_ROOT = "https://musicbrainz.org/ws/2/"
ROLES = {"Producer", "DJ", "Singer", "MC"}
INTEREST = {"keep", "exclude", "uncertain"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def snapshot(database: Path) -> dict[str, Any]:
    """Read the confirmed catalog in one SQLite transaction without app services."""
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        profiles = {
            row["artist_id"]: dict(row)
            for row in connection.execute(
                "SELECT artist_id,display_name FROM artists WHERE state='established'"
            )
        }
        credits: dict[str, list[dict]] = {}
        for row in connection.execute(
            "SELECT c.track_id,c.artist_id,c.position,c.role FROM track_artist_credits c "
            "JOIN artists a USING(artist_id) WHERE c.confirmed=1 AND a.state='established' "
            "ORDER BY c.track_id,c.position"
        ):
            credits.setdefault(row["track_id"], []).append(
                {
                    "artist_id": row["artist_id"],
                    "name": profiles[row["artist_id"]]["display_name"],
                    "credit_role": row["role"],
                }
            )
        tracks = []
        for row in connection.execute(
            "SELECT l.track_id,l.path,l.metadata_json,r.confirmed_title "
            "FROM track_locations l JOIN track_artist_review r USING(track_id) "
            "WHERE r.review_state='confirmed' ORDER BY l.track_id"
        ):
            if row["track_id"] not in credits:
                continue
            metadata = json.loads(row["metadata_json"])
            tracks.append(
                {
                    "track_id": row["track_id"],
                    "title": row["confirmed_title"] or "",
                    "path": row["path"],
                    "format": Path(row["path"]).suffix.lower(),
                    "observed_genres": metadata.get("genre", []),
                    "observed_artists": metadata.get("artist", []),
                    "credits": credits[row["track_id"]],
                }
            )
        return {"created_at": now(), "artists": list(profiles.values()), "tracks": tracks}
    finally:
        connection.close()


def motifs(track: dict) -> set[str]:
    title = track["title"].casefold()
    found = {"collaboration" if len(track["credits"]) > 1 else "single_credit"}
    if "remix" in title or any(c["credit_role"] == "remixer" for c in track["credits"]):
        found.add("remix")
    if re.search(r"\b(bootleg|flip|edit|refix)\b", title):
        found.add("bootleg_flip_edit")
    if any(len(c["name"]) <= 3 for c in track["credits"]):
        found.add("short_name")
    return found


def select_tracks(tracks: list[dict], selectors: list[dict], size: int, seed: int) -> tuple:
    if size < 1:
        raise ValueError("Sample size must be positive")
    population = sorted(tracks, key=lambda row: row["track_id"])
    random.Random(seed).shuffle(population)
    picked: dict[str, dict] = {}
    coverage = []
    for selector in selectors:
        names = {key(n) for n in selector.get("artists", [])}
        pattern = re.compile(selector.get("title_pattern", ".*"), re.I)
        eligible = [
            t
            for t in population
            if pattern.search(t["title"])
            and (not names or any(key(c["name"]) in names for c in t["credits"]))
        ]
        eligible.sort(key=lambda t: (len(t["credits"]), t["track_id"] not in picked))
        chosen = []
        for track in eligible:
            if len(chosen) >= selector.get("count", 1):
                break
            if track["track_id"] not in picked and len(picked) >= size:
                continue
            picked.setdefault(track["track_id"], {**track, "selection_categories": []})
            if selector["category"] not in picked[track["track_id"]]["selection_categories"]:
                picked[track["track_id"]]["selection_categories"].append(selector["category"])
            chosen.append(track["track_id"])
        coverage.append(
            {
                "category": selector["category"],
                "requested": selector.get("count", 1),
                "selected": len(chosen),
                "available": len(eligible),
            }
        )
    for category in ("remix", "bootleg_flip_edit", "collaboration", "single_credit", "short_name"):
        if not any(category in motifs(t) for t in picked.values()):
            for track in population:
                if category in motifs(track) and len(picked) < size:
                    picked[track["track_id"]] = {**track, "selection_categories": [category]}
                    break
    selected_artists = {c["artist_id"] for t in picked.values() for c in t["credits"]}
    population.sort(key=lambda t: sum(c["artist_id"] not in selected_artists for c in t["credits"]))
    for track in population:
        if len(picked) >= size:
            break
        picked.setdefault(track["track_id"], {**track, "selection_categories": ["additional"]})
    sample = list(picked.values())
    structural = Counter(m for t in sample for m in motifs(t))
    return sample, {
        "selectors": coverage,
        "structural": dict(structural),
        "missing_structural": [
            m
            for m in ("remix", "bootleg_flip_edit", "collaboration", "single_credit", "short_name")
            if not structural[m]
        ],
    }


def dossiers(catalog: dict, sample: list[dict]) -> list[dict]:
    ids = {c["artist_id"] for t in sample for c in t["credits"]}
    result = []
    for profile in sorted(
        catalog["artists"], key=lambda a: (key(a["display_name"]), a["artist_id"])
    ):
        if profile["artist_id"] not in ids:
            continue
        tracks = [
            t
            for t in catalog["tracks"]
            if any(c["artist_id"] == profile["artist_id"] for c in t["credits"])
        ]
        role_counts = Counter(
            c["credit_role"]
            for t in tracks
            for c in t["credits"]
            if c["artist_id"] == profile["artist_id"]
        )
        result.append(
            {
                **profile,
                "collection_tracks": len(tracks),
                "credit_roles": dict(role_counts),
                "representative_titles": sorted({t["title"] for t in tracks})[:6],
                "sample_tracks": [
                    t["track_id"]
                    for t in sample
                    if any(c["artist_id"] == profile["artist_id"] for c in t["credits"])
                ],
                "human_decision": "pending",
            }
        )
    return result


def prepare(database: Path, output: Path, selectors: list[dict], size: int, seed: int) -> dict:
    if output.exists():
        raise ValueError("Prepare requires a new output directory")
    catalog = snapshot(database)
    sample, coverage = select_tracks(catalog["tracks"], selectors, size, seed)
    artists = dossiers(catalog, sample)
    output.mkdir(parents=True)
    write_json(output / "catalog.json", catalog)
    write_json(output / "sample.json", sample)
    write_json(output / "artists.json", artists)
    manifest = {
        "version": VERSION,
        "created_at": now(),
        "source_database": str(database.resolve()),
        "seed": seed,
        "requested_tracks": size,
        "sample_tracks": len(sample),
        "sample_artists": len(artists),
        "catalog_tracks": len(catalog["tracks"]),
        "catalog_artists": len(catalog["artists"]),
        "coverage": coverage,
        "catalog_sha256": hashlib.sha256((output / "catalog.json").read_bytes()).hexdigest(),
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def lucene_name(name: str) -> str:
    escaped = re.sub(r'([+\-!(){}\[\]^"~*?:\\/|&])', r"\\\1", name)
    return 'artist:"' + escaped + '"'


class ProviderError(Exception):
    """An unsuccessful lookup; never converted into an empty artist list."""


class MusicBrainzClient:
    def __init__(
        self,
        cache: Path,
        *,
        interval: float = 1.1,
        timeout: float = 15,
        opener=urlopen,
        clock=time.monotonic,
        sleeper=time.sleep,
    ) -> None:
        if interval < 1:
            raise ValueError("MusicBrainz interval must be at least one second")
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)
        self.interval, self.timeout = interval, timeout
        self.opener, self.clock, self.sleeper = opener, clock, sleeper
        self.last_request: float | None = None
        self.requests = 0
        self.cache_hits = 0

    def get(self, resource: str, parameters: dict) -> dict:
        url = MB_ROOT + resource + "?" + urlencode({**parameters, "fmt": "json"})
        path = self.cache / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        if path.exists():
            try:
                cached = read_json(path)
                if isinstance(cached, dict) and cached.get("url") == url:
                    self.cache_hits += 1
                    return cached["response"]
            except (ValueError, KeyError):
                pass
        for attempt in range(3):
            if self.last_request is not None:
                self.sleeper(max(0, self.interval - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            self.requests += 1
            delay = min(2 ** (attempt + 1), 30)
            try:
                request = Request(
                    url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
                )
                with self.opener(request, timeout=self.timeout) as response:
                    data = response.read(2_000_001)
                if len(data) > 2_000_000:
                    raise ProviderError("Response exceeds size limit")
                try:
                    payload = json.loads(data)
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ProviderError("Invalid JSON response") from exc
                if not isinstance(payload, dict) or "error" in payload:
                    raise ProviderError("Invalid provider response")
                write_json(path, {"url": url, "retrieved_at": now(), "response": payload})
                return payload
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504):
                    raise ProviderError(f"HTTP {exc.code}") from exc
                retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
                if retry_after.isdigit():
                    delay = max(delay, int(retry_after))
                else:
                    if retry_after:
                        from email.utils import parsedate_to_datetime

                        with suppress(ValueError, TypeError):
                            delay = max(
                                delay,
                                (
                                    parsedate_to_datetime(retry_after) - datetime.now(UTC)
                                ).total_seconds(),
                            )
                if delay > 60 or attempt == 2:
                    raise ProviderError(f"HTTP {exc.code}; retry deferred") from exc
            except (URLError, TimeoutError, OSError) as exc:
                if attempt == 2:
                    raise ProviderError(type(exc).__name__) from exc
            self.sleeper(delay)
        raise ProviderError("Lookup failed")


def canonical_profile(url: str) -> str | None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        return None
    if host == "open.spotify.com" and re.fullmatch(r"/artist/[A-Za-z0-9]{22}/?", parsed.path):
        return urlunsplit(("https", host, parsed.path.rstrip("/"), "", ""))
    if (
        host in {"soundcloud.com", "www.soundcloud.com"}
        and re.fullmatch(r"/[A-Za-z0-9_-]+/?", parsed.path)
        and parsed.path.strip("/") not in {"search", "discover", "you", "charts"}
    ):
        return urlunsplit(("https", "soundcloud.com", parsed.path.rstrip("/"), "", ""))
    return None


def enrich_musicbrainz(output: Path, client: MusicBrainzClient) -> dict:
    path = output / "musicbrainz.json"
    checkpoint = read_json(path) if path.exists() else {"artists": {}, "runs": []}
    artists = read_json(output / "artists.json")
    started = time.monotonic()
    consecutive_errors = 0
    interrupted = False
    try:
        for index, artist in enumerate(artists):
            aid = artist["artist_id"]
            if checkpoint["artists"].get(aid, {}).get("status") == "succeeded":
                continue
            print(f"MusicBrainz {index + 1}/{len(artists)}: {artist['display_name']}", flush=True)
            try:
                search = client.get(
                    "artist/", {"query": lucene_name(artist["display_name"]), "limit": 5}
                )
                if not isinstance(search.get("artists"), list):
                    raise ProviderError("Artist search has no artists array")
                candidates = search["artists"]
                details = []
                exact = [
                    c
                    for c in candidates
                    if key(c.get("name", "")) == key(artist["display_name"])
                    or any(
                        key(a.get("name", "")) == key(artist["display_name"])
                        for a in c.get("aliases", [])
                    )
                ]
                for candidate in exact[:2]:
                    detail = client.get(
                        "artist/" + candidate["id"], {"inc": "aliases+url-rels+genres+tags"}
                    )
                    detail["profile_links"] = [
                        p
                        for rel in detail.get("relations", [])
                        if (p := canonical_profile(rel.get("url", {}).get("resource", "")))
                    ]
                    details.append(detail)
                checkpoint["artists"][aid] = {
                    "status": "succeeded",
                    "retrieved_at": now(),
                    "candidates": candidates,
                    "details": details,
                    "identity_status": "needs_audit",
                    "search_is_empty": not candidates,
                }
                consecutive_errors = 0
            except ProviderError as exc:
                checkpoint["artists"][aid] = {
                    "status": "error",
                    "error": str(exc),
                    "retrieved_at": now(),
                }
                consecutive_errors += 1
            write_json(path, checkpoint)
            if consecutive_errors >= 3:
                print("Provider paused after three consecutive errors; resume later.", flush=True)
                break
    except KeyboardInterrupt:
        interrupted = True
    checkpoint["runs"].append(
        {
            "at": now(),
            "seconds": round(time.monotonic() - started, 3),
            "http_requests": client.requests,
            "cache_hits": client.cache_hits,
            "interrupted": interrupted,
        }
    )
    write_json(path, checkpoint)
    return checkpoint


def validate_observations(observations: list[dict], artists: list[dict]) -> dict:
    known = {a["artist_id"] for a in artists}
    indexed = {}
    for row in observations:
        aid = row["artist_id"]
        if aid not in known or aid in indexed:
            raise ValueError("Unknown or duplicated artist observation")
        if set(row.get("roles", [])) - ROLES:
            raise ValueError("Unsupported role")
        if row.get("interest_proposal", "uncertain") not in INTEREST:
            raise ValueError("Unsupported interest proposal")
        if row.get("bass_related") not in (True, False, None):
            raise ValueError("Bass-related must be true, false or null")
        sources = row.get("sources", [])
        if any(urlsplit(s["url"]).scheme != "https" for s in sources):
            raise ValueError("Sources require HTTPS URLs")
        if (
            row.get("roles")
            or row.get("links")
            or row.get("bass_related") is not None
            or row.get("interest_proposal", "uncertain") != "uncertain"
        ) and not sources:
            raise ValueError("Enrichment proposals require evidence")
        for link in row.get("links", []):
            if not canonical_profile(link["url"]) or not link.get("evidence_url"):
                raise ValueError("Profiles require a canonical link and evidence URL")
            if link["evidence_url"] not in {s["url"] for s in sources}:
                raise ValueError("Profile evidence must appear in sources")
        indexed[aid] = row
    return indexed


def md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def make_report(output: Path, observations: list[dict]) -> dict:
    manifest, sample, artists = (
        read_json(output / n) for n in ("manifest.json", "sample.json", "artists.json")
    )
    audited = validate_observations(observations, artists)
    mb_path = output / "musicbrainz.json"
    mb = read_json(mb_path) if mb_path.exists() else {"artists": {}, "runs": []}
    counts = Counter(v.get("status", "not_attempted") for v in mb["artists"].values())
    summary = {
        "tracks": len(sample),
        "artists": len(artists),
        "web_audited": len(audited),
        "musicbrainz": dict(counts),
        "musicbrainz_not_attempted": len(artists) - len(mb["artists"]),
        "human_review": "pending",
        "proposed_interest": dict(
            Counter(o.get("interest_proposal", "uncertain") for o in audited.values())
        ),
        "proposed_roles": dict(Counter(r for o in audited.values() for r in o.get("roles", []))),
        "provider_runs": mb["runs"],
        "tokens": "not_exposed_by_tools",
        "price": "not_measured",
        "coverage": manifest["coverage"],
    }
    write_json(output / "observations.json", observations)
    write_json(output / "summary.json", summary)
    review = output / "human-review.csv"
    if not review.exists():
        with review.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "artist_id",
                    "artist",
                    "interest_proposal",
                    "roles_proposed",
                    "human_decision",
                    "roles_corrected",
                    "notes",
                ],
            )
            writer.writeheader()
            for artist in artists:
                row = audited.get(artist["artist_id"], {})
                writer.writerow(
                    {
                        "artist_id": artist["artist_id"],
                        "artist": artist["display_name"],
                        "interest_proposal": row.get("interest_proposal", "uncertain"),
                        "roles_proposed": ";".join(row.get("roles", [])),
                        "human_decision": "pending",
                        "roles_corrected": "",
                        "notes": "",
                    }
                )
    lines = [
        "# Pilote artistes — 50 morceaux",
        "",
        f"{len(sample)} morceaux distincts ; {len(artists)} artistes. Revue humaine à faire.",
        "",
        "Les catégories de sélection et classements ci-dessous sont des propositions. "
        "Aucun suivi Spotify ni changement de crédit, tag, fichier ou base MTEE.",
        "",
        "## Couverture",
        "",
        "```json",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Les morceaux",
        "",
        "| # | Artistes | Titre confirmé local | Catégories de sélection |",
        "|---|---|---|---|",
    ]
    for index, track in enumerate(sample, 1):
        lines.append(
            f"| {index} | {md(', '.join(c['name'] for c in track['credits']))} | "
            f"{md(track['title'])} | {md(', '.join(track['selection_categories']))} |"
        )
    lines += ["", "## Audit des artistes", ""]
    for artist in artists:
        aid = artist["artist_id"]
        observation = audited.get(aid, {})
        provider = mb["artists"].get(aid, {})
        lines += [
            f"### {md(artist['display_name'])}",
            "",
            f"{artist['collection_tracks']} morceaux dans la collection. "
            f"Rôles proposés : {', '.join(observation.get('roles', [])) or 'non établis'}. "
            f"Bass-related : {observation.get('bass_related')}. "
            f"Tri proposé : {observation.get('interest_proposal', 'uncertain')}.",
            "",
            observation.get("reason", "Recherche/audit non réalisé."),
            "",
            f"Identité : {observation.get('identity_status', 'not_audited')}. "
            f"MusicBrainz : {provider.get('status', 'not_attempted')} "
            f"({len(provider.get('candidates', []))} candidats).",
            "",
        ]
        for detail in provider.get("details", []):
            lines.append(
                f"- Candidat MusicBrainz : [{md(detail.get('name', ''))}]"
                f"(https://musicbrainz.org/artist/{detail['id']}) ; "
                f"{md(detail.get('disambiguation', ''))}. Genres bruts : "
                f"{md(', '.join(g['name'] for g in detail.get('genres', [])))}."
            )
        for link in observation.get("links", []):
            lines.append(f"- Profil : [{md(link.get('label', 'Lien'))}]({link['url']}).")
        for source in observation.get("sources", []):
            lines.append(
                f"- Preuve : [{md(source.get('title', 'Source'))}]({source['url']}) — "
                f"{md(source.get('supports', ''))}."
            )
        for issue in observation.get("issues", []):
            lines.append(f"- À vérifier : {md(issue)}")
        lines.append("")
    lines += [
        "## Revue utilisateur",
        "",
        "Renseigner human-review.csv : keep/exclude/uncertain dans human_decision, "
        "corriger les rôles si besoin et ajouter des notes. Ce fichier reste indépendant "
        "de MTEE ; il n'est pas écrasé lors de la régénération du rapport.",
        "",
        "Les genres observés ne classent pas les morceaux. Le coût de recherche, "
        "les tokens et les tarifs non exposés ne sont pas annoncés comme mesurés.",
        "",
    ]
    (output / "rapport.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--database", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--selectors", type=Path)
    prepare_parser.add_argument("--size", type=int, default=50)
    prepare_parser.add_argument("--seed", type=int, default=105)
    network_parser = commands.add_parser("musicbrainz")
    network_parser.add_argument("--output", type=Path, required=True)
    report_parser = commands.add_parser("report")
    report_parser.add_argument("--output", type=Path, required=True)
    report_parser.add_argument("--observations", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(
            args.database,
            args.output,
            read_json(args.selectors) if args.selectors else [],
            args.size,
            args.seed,
        )
    elif args.command == "musicbrainz":
        result = enrich_musicbrainz(args.output, MusicBrainzClient(args.output / "cache"))
        result = {"processed": len(result["artists"]), "runs": result["runs"]}
    else:
        result = make_report(args.output, read_json(args.observations))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
