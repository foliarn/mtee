"""Read-only local inventory and reproducible sample for ExecPlan 102.

This study helper deliberately does not import the MTEE application or its
metadata writer. Its JSON output contains private collection paths and must
remain in the ignored ``.local`` directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter
from collections.abc import Iterable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from mutagen import File as MutagenFile
from mutagen.id3 import ID3

from mtee.services.metadata_reader import MetadataReader

SUPPORTED = {".mp3", ".flac", ".wav", ".aif", ".aiff", ".m4a"}
FIELDS = {
    "title": ("TIT2", "©nam", "title"),
    "artist": ("TPE1", "©ART", "artist"),
    "album": ("TALB", "©alb", "album"),
    "album_artist": ("TPE2", "aART", "albumartist", "album artist"),
    "genre": ("TCON", "©gen", "genre"),
    "date": ("TDRC", "TYER", "©day", "date", "year"),
    "bpm": ("TBPM", "tmpo", "bpm"),
    "key": ("TKEY", "initialkey", "key"),
}
MUSIC_MARKERS = ("spotify", "soundcloud", "musicbrainz", "discogs", "bandcamp")
MUSIC_HOSTS = {
    "spotify.com",
    "open.spotify.com",
    "soundcloud.com",
    "musicbrainz.org",
    "bandcamp.com",
    "discogs.com",
    "tidal.com",
}
SECRET_MARKERS = ("token", "secret", "auth", "cookie", "signature", "signed")
VERSION_RE = re.compile(r"\b(remix|edit|bootleg|live|extended|club mix|radio edit|vip)\b", re.I)
SEPARATORS_RE = re.compile(r"\s(?:-|–|—|\|)\s|\s+[/&+]\s+|\bfeat\.?\b", re.I)  # noqa: RUF001

PROMO_RE = re.compile(
    r"\b(?:free\s+(?:download|dl)|download\s+free|promo(?:tional)?\s+copy|"
    r"out\s+now|buy\s+link\s+in\s+description)\b",
    re.I,
)
TECHNICAL_RE = re.compile(
    r"\b(?:(?:\d{2,3}\s*)?kbps|(?:16|24)\s*bit|"
    r"(?:44\.1|48|88\.2|96)\s*khz)\b",
    re.I,
)
FINAL_MARKER_RE = re.compile(
    r"(?:\s*[-\u2013\u2014]\s*|\s+)(?:final\s*\d*|master(?:ed)?|wav(?:\s+file)?)\s*$", re.I
)
VERSION_DETAIL_RE = re.compile(
    r"\b(?:remix|rework|edit|bootleg|live|extended(?:\s+mix)?|club\s+mix|"
    r"radio\s+edit|vip|original\s+mix|instrumental|dub\s+mix|refix|flip)\b",
    re.I,
)
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
WINDOWS_INVALID_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _clean_annotation(text: str) -> tuple[str, list[str], list[str]]:
    """Remove only clearly non-musical title annotations and report uncertainty."""
    removed: list[str] = []
    ambiguous: list[str] = []

    def remove_match(match: re.Match[str]) -> str:
        value = match.group(0)
        if (
            PROMO_RE.search(value)
            or TECHNICAL_RE.search(value)
            or re.search(r"\b(?:final\s*\d*|master(?:ed)?|wav(?:\s+file)?)\b", value, re.I)
        ):
            removed.append(value.strip(" ()[]{}"))
            return " "
        # Catalog-like codes are removed only when their shape is explicit.
        if re.fullmatch(r"[A-Z]{2,8}[-_ ]?\d{2,6}[A-Z]?", value.strip(" ()[]{}"), re.I):
            removed.append(value.strip(" ()[]{}"))
            return " "
        if not VERSION_DETAIL_RE.search(value):
            ambiguous.append(value.strip(" ()[]{}"))
        return value

    text = re.sub(r"\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}", remove_match, text)
    text = PROMO_RE.sub(lambda m: removed.append(m.group(0)) or " ", text)
    text = TECHNICAL_RE.sub(lambda m: removed.append(m.group(0)) or " ", text)
    match = FINAL_MARKER_RE.search(text)
    if match:
        removed.append(match.group(0).strip(" -\u2013\u2014"))
        text = text[: match.start()]
    # Numeric year/version tokens are not confidently classifiable as noise.
    for match in re.finditer(r"\b(?:19|20)\d{2}\b|\bv\d+(?:\.\d+)*\b", text, re.I):
        if not VERSION_DETAIL_RE.search(text[max(0, match.start() - 24) : match.end() + 24]):
            ambiguous.append(match.group(0))
    cleaned = re.sub(r"\s+", " ", text).strip(" \t-\u2013\u2014_.,;:")
    return cleaned, removed, ambiguous


def _artist_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _windows_path_key(value: str) -> str:
    """Approximate Windows case-insensitive path identity, including trailing dots/spaces."""
    return "/".join(part.rstrip(" .").casefold() for part in value.replace("\\", "/").split("/"))


def _artist_components(value: str, known: set[str]) -> list[str]:
    """Split collaboration punctuation only when every part is independently known."""
    parts = re.split(r"\s*(?:,|&|\band\b|\bfeat\.?|\bft\.?)\s*", value, flags=re.I)
    if len(parts) > 1 and all(_artist_key(part) in known for part in parts):
        return [part.strip() for part in parts]
    if _artist_key(value) in known:
        return [value.strip()]
    return [value.strip()] if value.strip() else []


def same_artist_credit(left: str, right: str, known_artists: Iterable[str]) -> bool:
    """Compare collaboration credits as artist lists, independent of separator."""
    known = {_artist_key(name) for name in known_artists}
    known.update({_artist_key(left), _artist_key(right)})
    left_parts = [_artist_key(x) for x in _artist_components(left, known)]
    right_parts = [_artist_key(x) for x in _artist_components(right, known)]
    return sorted(left_parts) == sorted(right_parts)


def _parse_filename_metadata(
    filename: str, known_artists: Iterable[str]
) -> tuple[list[str], str, list[str]]:
    """Parse known artist prefixes without splitting hyphens inside artist names."""
    stem = Path(filename).stem
    known = sorted(set(known_artists), key=lambda item: (-len(item), item.casefold()))
    folded = stem.casefold()
    for artist in known:
        prefix = artist.casefold()
        if not folded.startswith(prefix):
            continue
        remainder = stem[len(artist) :]
        match = re.match(r"^\s*(?:-|\u2013|\u2014|\|)\s*(.+)$", remainder)
        if match:
            return (
                _artist_components(artist, {_artist_key(x) for x in known}),
                match.group(1).strip(),
                [],
            )
    # A known artist may also appear in the title tag as "ARTIST - TITLE".
    return [], stem, []


def propose_metadata(row: dict[str, Any], known_artists: Iterable[str]) -> dict[str, Any]:
    """Propose cleaned artist/title values while retaining every existing value."""
    tags = row.get("tags", {})
    raw_artists = [str(value) for value in tags.get("artist", [])]
    raw_titles = [str(value) for value in tags.get("title", [])]
    tag_artists = [value.strip() for value in raw_artists if value.strip()]
    tag_titles = [value for value in raw_titles if value.strip()]
    known = {_artist_key(name) for name in known_artists}
    known.update(_artist_key(name) for name in tag_artists)
    filename_artists, filename_title, _ = _parse_filename_metadata(
        Path(row.get("relative_path", "")).name, known_artists
    )

    proposed_artists = list(tag_artists) if tag_artists else filename_artists
    artist_evidence = "artist_tag_values" if tag_artists else "known_artist_filename_prefix"
    artist_keys = {
        _artist_key(value)
        for artist in proposed_artists
        for value in _artist_components(artist, known)
    }
    title_sources = tag_titles if tag_titles else [filename_title]
    proposed_titles: list[str] = []
    removed: list[str] = []
    ambiguous: list[str] = []
    for raw_title in title_sources:
        title = raw_title
        # Strip a leading artist credit only when the entire prefix is in the proposed credit list.
        match = re.match(r"^\s*(.+?)\s+-\s+(.+)$", title)
        prefix_keys = (
            {_artist_key(value) for value in _artist_components(match.group(1), known)}
            if match
            else set()
        )
        if match and prefix_keys and prefix_keys == artist_keys:
            title = match.group(2)
        # Title can be the only place where a known artist and its track are credited.
        if not proposed_artists:
            title_artists, remainder, _ = _parse_filename_metadata(title, known_artists)
            if title_artists:
                proposed_artists = title_artists
                title = remainder
                artist_evidence = "known_artist_prefix_in_title_tag"
            else:
                unverified = re.match(
                    r"^\s*([A-Z][A-Z0-9&+.,'\u2019 -]{1,50}?)\s+[-\u2013\u2014]\s+(.+)$",
                    title,
                )
                if unverified and unverified.group(1).strip().isupper():
                    proposed_artists = [unverified.group(1).strip()]
                    title = unverified.group(2)
                    artist_evidence = "uppercase_artist_prefix_in_title_tag_unverified"
        cleaned, dropped, uncertain = _clean_annotation(title)
        removed.extend(dropped)
        ambiguous.extend(uncertain)
        if cleaned:
            proposed_titles.append(cleaned)

    raw_text = " ".join(tag_artists + tag_titles + [Path(row.get("relative_path", "")).name])
    corrupt = bool("\ufffd" in raw_text or re.search(r"(?:Ã.|Â.|â€|ðŸ)", raw_text))
    if corrupt:
        ambiguous.append("possible_encoding_corruption")
    return {
        "proposed_artists": proposed_artists,
        "proposed_titles": proposed_titles,
        "artist_evidence_basis": artist_evidence,
        "existing_artists": raw_artists,
        "existing_titles": raw_titles,
        "removed_annotations": sorted(set(removed)),
        "ambiguous_annotations": sorted(set(ambiguous)),
        "encoding_warning": corrupt,
        "verification_status": "not_checked",
    }


def simulate_rename_proposals(
    inventory: list[dict[str, Any]], proposals: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Preview Windows-safe title.ext targets and collisions without changing files."""
    existing: dict[str, list[str]] = {}
    for row in inventory:
        path = row.get("relative_path", "")
        existing.setdefault(_windows_path_key(path), []).append(path)
    targets: dict[str, list[str]] = {}
    result: list[dict[str, Any]] = []
    for row in inventory:
        item_id = row.get("item_id", "")
        proposal = proposals.get(item_id, {})
        titles = proposal.get("proposed_titles", [])
        extension = Path(row.get("relative_path", "")).suffix
        candidates = [f"{title}{extension}" for title in titles]
        result.append(
            {
                "item_id": item_id,
                "current_relative_path": row.get("relative_path", ""),
                "candidate_filenames": candidates,
                "rename_applied": False,
            }
        )
        for candidate in candidates:
            key = _windows_path_key(
                (Path(row.get("relative_path", "")).parent / candidate).as_posix()
            )
            targets.setdefault(key, []).append(item_id)
    for row, preview in zip(inventory, result, strict=True):
        source = row.get("relative_path", "")
        collisions: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []
        for candidate in preview["candidate_filenames"]:
            target = (Path(source).parent / candidate).as_posix()
            key = _windows_path_key(target)
            if any(
                path != source and _windows_path_key(path) == key for path in existing.get(key, [])
            ):
                collisions.append({"target": target, "kind": "existing_file"})
            if len(set(targets.get(key, []))) > 1:
                collisions.append({"target": target, "kind": "proposed_target"})
            base = Path(candidate).stem
            if (
                WINDOWS_INVALID_RE.search(candidate)
                or base.rstrip(" .") != base
                or base.upper() in WINDOWS_RESERVED
                or len(candidate) > 255
            ):
                issues.append({"filename": candidate, "kind": "invalid_windows_name"})
        preview["collisions"] = collisions
        preview["windows_name_issues"] = issues
    return result


def _stat(path: Path) -> dict[str, int | None]:
    try:
        value = path.stat(follow_symlinks=False)
        return {"size_bytes": value.st_size, "mtime_ns": value.st_mtime_ns}
    except OSError:
        return {"size_bytes": None, "mtime_ns": None}


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def _roots(values: list[str]) -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for index, value in enumerate(values, 1):
        root = Path(value).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"Root is not a directory: {value}")
        result.append((f"R{index}", root))
    return result


def _walk(
    roots: list[tuple[str, Path]], output: Path
) -> tuple[list[tuple[str, Path, Path]], Counter[str]]:
    found: list[tuple[str, Path, Path]] = []
    other: Counter[str] = Counter()
    seen: set[str] = set()
    output_resolved = output.resolve(strict=False)
    for alias, root in roots:
        for base, dirs, names in os.walk(root, followlinks=False):
            current = Path(base)
            dirs[:] = sorted(
                name
                for name in dirs
                if not _is_link_or_junction(current / name)
                and not _inside(output_resolved, (current / name).resolve(strict=False))
            )
            for name in sorted(names):
                path = current / name
                if _is_link_or_junction(path):
                    continue
                suffix = path.suffix.casefold()
                if suffix not in SUPPORTED:
                    other[suffix or "[sans extension]"] += 1
                    continue
                resolved = str(path.resolve(strict=False)).casefold()
                if resolved in seen:
                    continue
                seen.add(resolved)
                found.append((alias, root, path))
    found.sort(
        key=lambda row: (
            row[0],
            row[2].relative_to(row[1]).as_posix().casefold(),
            row[2].relative_to(row[1]).as_posix(),
        )
    )
    return found, other


def _text(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [
            _text(item)[0] if isinstance(item, (bytes, bytearray)) else str(item) for item in value
        ]
    if isinstance(value, bytes):
        return [value.decode("utf-8", errors="replace")]
    text = getattr(value, "text", None)
    if text is not None:
        return _text(text)
    data = getattr(value, "data", None)
    if isinstance(data, bytes):
        return [data.decode("utf-8", errors="replace")]
    return [str(value)]


def _values(tags: Any, keys: Iterable[str]) -> list[str]:
    if tags is None:
        return []
    output: list[str] = []
    for key in keys:
        try:
            value = tags.get(key)
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        if value is not None:
            output.extend(_text(value))
    return output


def _music_refs(tags: Any, names: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    urls: set[str] = set()
    identifiers: set[tuple[str, str]] = set()
    for key in names:
        folded = key.casefold()
        relevant_key = any(marker in folded for marker in MUSIC_MARKERS)
        if any(marker in folded for marker in SECRET_MARKERS):
            continue
        for value in _values(tags, (key,)):
            text = value.strip()
            if text.startswith(("http://", "https://")):
                try:
                    parsed = urlsplit(text)
                    host = (parsed.hostname or "").casefold()
                except ValueError:
                    continue
                recognized_host = any(
                    host == domain or host.endswith(f".{domain}") for domain in MUSIC_HOSTS
                )
                if parsed.scheme not in {"http", "https"} or not recognized_host:
                    continue
                urls.add(urlunsplit((parsed.scheme, host, parsed.path, "", "")))
            elif relevant_key and text and len(text) <= 256 and not any(c.isspace() for c in text):
                identifiers.add((key, text))
    return sorted(urls), [{"source_key": key, "value": value} for key, value in sorted(identifiers)]


def _raw_tags(
    path: Path,
) -> tuple[dict[str, list[str]], list[str], list[str], list[dict[str, str]]]:
    audio = MutagenFile(path, easy=False)
    tags = getattr(audio, "tags", None)
    values = {field: _values(tags, keys) for field, keys in FIELDS.items()}
    names: list[str] = []
    urls: list[str] = []
    identifiers: list[dict[str, str]] = []
    if tags is not None:
        with suppress(AttributeError, TypeError):
            names = sorted(str(key) for key in tags)
        urls, identifiers = _music_refs(tags, names)
    return values, names, urls, identifiers


def _inventory_one(alias: str, root: Path, path: Path) -> dict[str, Any]:
    before = _stat(path)
    relative = path.relative_to(root).as_posix()
    record: dict[str, Any] = {
        "item_id": hashlib.sha256(f"{alias}\0{relative}".encode()).hexdigest()[:16],
        "root_alias": alias,
        "relative_path": relative,
        "extension": path.suffix.casefold(),
        "before": before,
        "container": path.suffix.removeprefix(".").upper(),
        "codec": None,
        "duration_seconds": None,
        "status": "unreadable",
        "error": None,
        "tags": {name: [] for name in FIELDS},
        "mtee_view": {},
        "tag_names": [],
        "music_urls": [],
        "music_identifiers": [],
        "id3_version": None,
        "changed_during_read": False,
        "hard_link_count": None,
    }
    try:
        if path.suffix.casefold() == ".mp3":
            try:
                id3 = ID3(path)
                record["id3_version"] = f"{id3.version[0]}.{id3.version[1]}.{id3.version[2]}"
            except Exception:
                pass
        audio = MutagenFile(path, easy=False)
        if audio is None or getattr(audio, "info", None) is None:
            raise ValueError("Mutagen could not identify a supported audio stream")
        raw, names, urls, identifiers = _raw_tags(path)
        record["tags"], record["tag_names"], record["music_urls"] = raw, names, urls
        record["music_identifiers"] = identifiers
        snapshot = MetadataReader().read(path)
        record["mtee_view"] = {
            field: list(getattr(snapshot, field))
            for field in (
                "title",
                "artist",
                "album",
                "genre",
                "date",
                "bpm",
                "key",
                "track_number",
                "comment",
            )
        }
        record["mtee_status"] = snapshot.status
        record["codec"] = type(audio).__name__
        duration = getattr(audio.info, "length", None)
        record["duration_seconds"] = float(duration) if duration is not None else None
        record["status"] = "readable"
    except Exception as exc:  # Keep damaged and unsupported files in the inventory.
        record["error"] = f"{type(exc).__name__}: {exc}"
    after = _stat(path)
    record["after"] = after
    record["changed_during_read"] = before != after or after["size_bytes"] is None
    with suppress(OSError):
        record["hard_link_count"] = path.stat(follow_symlinks=False).st_nlink
    return record


def _motifs(row: dict[str, Any]) -> list[str]:
    tags = row.get("tags", {})
    title = " ".join(tags.get("title", [])).strip()
    artist = " ".join(tags.get("artist", [])).strip()
    stem = Path(row.get("relative_path", "")).stem
    motifs: list[str] = []
    if not title and not artist:
        motifs.append("title_and_artist_missing")
    elif not artist:
        motifs.append("artist_only_missing")
    if title and stem.casefold() != title.casefold():
        motifs.append("title_filename_divergence")
    if SEPARATORS_RE.search(stem) or len(tags.get("artist", [])) > 1:
        motifs.append("compound_credits_or_separators")
    if VERSION_RE.search(title + " " + stem):
        motifs.append("version_marker")
    if len(tags.get("artist", [])) > 1 or row.get("music_urls"):
        motifs.append("multiple_values_or_external_provenance")
    if not motifs and row.get("status") == "unreadable":
        motifs.append("unreadable")
    return motifs


def select_sample(
    rows: list[dict[str, Any]], seed: int = 102, random_size: int = 100, targeted_size: int = 50
) -> list[dict[str, Any]]:
    """Select stable random and targeted groups from a frozen inventory."""
    ordered = [
        dict(row)
        for row in sorted(
            rows,
            key=lambda r: (r["root_alias"], r["relative_path"].casefold(), r["relative_path"]),
        )
    ]
    rng = random.Random(seed)
    random_rows = rng.sample(ordered, min(random_size, len(ordered)))
    random_ids = {row["item_id"] for row in random_rows}
    for row in random_rows:
        row["sample_group"] = "random"
        row["sample_motifs"] = []
    remaining = [row for row in ordered if row["item_id"] not in random_ids]
    targeted: list[dict[str, Any]] = []
    targeted_ids: set[str] = set()

    def add_candidates(candidates: list[dict[str, Any]], limit: int, priority: int) -> None:
        nonlocal targeted
        available = [r for r in candidates if r["item_id"] not in random_ids | targeted_ids]
        stable_rng = random.Random(seed ^ 0x102A7)
        stable_rng.shuffle(available)
        for row in available[: max(0, limit)]:
            motifs = _motifs(row)
            row["sample_group"] = "targeted"
            row["sample_motifs"] = motifs
            row["sample_priority"] = priority
            targeted.append(row)
            targeted_ids.add(row["item_id"])

    budget = min(targeted_size, max(0, len(ordered) - len(random_rows)))
    # Fill rare formats toward five total examples, rarest first.
    counts = Counter(Path(r["relative_path"]).suffix.casefold() for r in ordered)
    included = Counter(Path(r["relative_path"]).suffix.casefold() for r in random_rows)
    for extension, _ in sorted(counts.items(), key=lambda pair: (pair[1], pair[0])):
        need = max(0, min(5, counts[extension]) - included[extension])
        add_candidates(
            [r for r in remaining if Path(r["relative_path"]).suffix.casefold() == extension],
            min(need, budget - len(targeted)),
            1,
        )
    for priority, predicate, quota in (
        (2, lambda m: "title_and_artist_missing" in m, 15),
        (2, lambda m: "artist_only_missing" in m, 15),
        (
            3,
            lambda m: bool(
                {"title_filename_divergence", "compound_credits_or_separators", "version_marker"}
                & set(m)
            ),
            15,
        ),
        (
            4,
            lambda m: bool({"multiple_values_or_external_provenance", "unreadable"} & set(m)),
            budget,
        ),
    ):
        if len(targeted) >= budget:
            break
        eligible = [r for r in remaining if predicate(_motifs(r))]
        add_candidates(eligible, min(quota, budget - len(targeted)), priority)
    add_candidates(remaining, budget - len(targeted), 5)
    return random_rows + targeted


def _dump_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_report(
    output: Path, run: dict[str, Any], inventory: list[dict[str, Any]], sample: list[dict[str, Any]]
) -> None:
    readable = [r for r in inventory if r["status"] == "readable" and not r["changed_during_read"]]
    random_rows = [r for r in sample if r["sample_group"] == "random"]
    targeted = [r for r in sample if r["sample_group"] == "targeted"]
    missing_title = sum(not any(v.strip() for v in r["tags"]["title"]) for r in readable)
    missing_artist = sum(not any(v.strip() for v in r["tags"]["artist"]) for r in readable)
    summary = {
        "observed_files": len(inventory),
        "readable_stable_files": len(readable),
        "unreadable_files": sum(r["status"] == "unreadable" for r in inventory),
        "changed_during_read": sum(r["changed_during_read"] for r in inventory),
        "formats": dict(sorted(Counter(r["extension"] for r in inventory).items())),
        "title_missing_readable_stable": {"count": missing_title, "denominator": len(readable)},
        "artist_missing_readable_stable": {"count": missing_artist, "denominator": len(readable)},
        "sample_groups": {"random": len(random_rows), "targeted": len(targeted)},
        "identification_review": "not_started; local evidence is not identity confirmation",
    }
    (output / "run.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _dump_jsonl(output / "inventory.jsonl", inventory)
    _dump_jsonl(output / "sample.jsonl", sample)
    (output / "review.jsonl").write_text("", encoding="utf-8")
    (output / "artist_candidates.json").write_text(
        json.dumps({"candidates": [], "status": "manual_review_pending"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "rename_preview.jsonl").write_text("", encoding="utf-8")
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    format_summary = (
        ", ".join(f"{key} {value}" for key, value in summary["formats"].items()) or "aucun"
    )
    report = [
        "# Rapport de l'étude mapping/tagging — brouillon d'inventaire",
        "",
        f"- Date UTC : {run['created_at_utc']}",
        f"- Fichiers observés : {len(inventory)} (estimation annoncée : environ 2 850)",
        f"- Formats : {format_summary}",
        f"- Lisibles et stables : {len(readable)} ; illisibles : {summary['unreadable_files']} ; "
        f"modifiés pendant la lecture : {summary['changed_during_read']}",
        f"- Titre absent : {missing_title}/{len(readable)} fichiers lisibles et stables.",
        f"- Artiste absent : {missing_artist}/{len(readable)} fichiers lisibles et stables.",
        f"- Échantillon figé : {len(random_rows)} aléatoires et {len(targeted)} ciblés.",
        "",
        "L'examen humain des propositions n'est pas commencé. Ces mesures ne confirment aucune "
        "identité musicale ; la compatibilité Rekordbox n'a pas été testée.",
        "Les fichiers détaillés de cette exécution contiennent des chemins de collection privés. "
        "Vérifier leur destination avant tout partage.",
    ]
    (output / "rapport-retour.md").write_text("\n".join(report) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> Path:
    output = Path(args.output).expanduser().resolve(strict=False)
    if output.exists():
        raise FileExistsError(f"Output directory already exists: {output}")
    if args.inventory_input:
        if args.root:
            raise ValueError("--inventory-input is incompatible with --root")
        with Path(args.inventory_input).open(encoding="utf-8") as handle:
            inventory = [json.loads(line) for line in handle if line.strip()]
        for row in inventory:
            row.setdefault("changed_during_read", False)
            row.setdefault("status", "unreadable")
            row.setdefault("extension", Path(row.get("relative_path", "")).suffix.casefold())
            row.setdefault("tags", {})
            for field in FIELDS:
                row["tags"].setdefault(field, [])
            row.setdefault("music_urls", [])
            row.setdefault("music_identifiers", [])
        roots: list[tuple[str, Path]] = []
        other: Counter[str] = Counter()
    else:
        if not args.root:
            raise ValueError("Provide at least one --root, or use --inventory-input")
        roots = _roots(args.root)
        for _, root in roots:
            if _inside(output, root):
                raise ValueError("Output directory must be outside every scanned root")
        paths, other = _walk(roots, output)
        inventory = [_inventory_one(alias, root, path) for alias, root, path in paths]
    output.mkdir(parents=True, exist_ok=False)
    sample = select_sample(inventory, args.seed, args.random_size, args.targeted_size)
    run_record = {
        "script_version": "102.4",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "python_version": sys.version,
        "mutagen_version": __import__("mutagen").version_string,
        "seed": args.seed,
        "random_size_requested": args.random_size,
        "targeted_size_requested": args.targeted_size,
        "roots": [{"alias": alias, "path": str(root)} for alias, root in roots],
        "other_extensions": dict(sorted(other.items())),
        "inventory_reused": bool(args.inventory_input),
        "inventory_input": str(Path(args.inventory_input).resolve())
        if args.inventory_input
        else None,
        "git_commit": _git_commit(),
    }
    _write_report(output, run_record, inventory, sample)
    return output


def _git_commit() -> str | None:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", action="append", help="Audio collection root; repeatable")
    result.add_argument(
        "--output", required=True, help="New private output directory outside all roots"
    )
    result.add_argument("--seed", type=int, default=102)
    result.add_argument("--random-size", type=int, default=100)
    result.add_argument("--targeted-size", type=int, default=50)
    result.add_argument(
        "--inventory-input", help="Reuse a frozen inventory.jsonl without rescanning"
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if args.random_size < 0 or args.targeted_size < 0:
        parser().error("sample sizes must be non-negative")
    try:
        print(run(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
