"""Invented library shown by the UX prototype.

Every title, artist, path and size here is fictitious. The set deliberately
contains long titles, accented names, missing tags and missing artwork so the
review exercises those cases. Nothing in this module reads or names a real file.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CONVERT_BATCHES",
    "FOLDERS",
    "PLAYLISTS",
    "ROOT_FOLDER",
    "TASKS",
    "TRACKS",
    "DemoFolder",
    "DemoPlaylist",
    "DemoTrack",
]


@dataclass(frozen=True, slots=True)
class DemoTrack:
    """One fictitious audio file with its tags and technical details."""

    track_id: str
    folder: str
    title: str
    artist: str
    album: str
    genre: str
    bpm: str
    key: str
    seconds: int
    audio_format: str
    bitrate: str
    sample_rate: str
    size_mb: float
    filename: str
    date_added: str
    cover: int  # index of a generated cover pattern, -1 when the file has none
    year: str = ""
    track_number: str = ""
    comment: str = ""


@dataclass(frozen=True, slots=True)
class DemoFolder:
    folder_id: str
    name: str
    parent: str


@dataclass(frozen=True, slots=True)
class DemoPlaylist:
    playlist_id: str
    name: str
    track_ids: tuple[str, ...]


ROOT_FOLDER = DemoFolder("music", "Music", "")

FOLDERS = (
    ROOT_FOLDER,
    DemoFolder("dubstep", "dubstep", "music"),
    DemoFolder("dnb", "dnb", "music"),
    DemoFolder("ukg", "ukg", "music"),
    DemoFolder("techno", "techno", "music"),
    DemoFolder("samples", "Échantillons d'été", "music"),
)


def _t(
    track_id: str,
    folder: str,
    title: str,
    artist: str,
    album: str,
    genre: str,
    bpm: str,
    key: str,
    seconds: int,
    audio_format: str,
    cover: int,
    date_added: str = "30 Jan 2026",
    filename: str | None = None,
) -> DemoTrack:
    bitrate, sample_rate, per_second = {
        "FLAC": ("1,012 kbps", "44.1 kHz", 0.124),
        "WAV": ("1,411 kbps", "44.1 kHz", 0.176),
        "MP3": ("320 kbps", "44.1 kHz", 0.040),
        "AIFF": ("1,411 kbps", "44.1 kHz", 0.176),
    }[audio_format]
    stem = filename or title.lower().replace(" ", "_").replace("'", "")
    return DemoTrack(
        track_id=track_id,
        folder=folder,
        title=title,
        artist=artist,
        album=album,
        genre=genre,
        bpm=bpm,
        key=key,
        seconds=seconds,
        audio_format=audio_format,
        bitrate=bitrate,
        sample_rate=sample_rate,
        size_mb=round(seconds * per_second, 1),
        filename=f"{stem}.{audio_format.lower()}",
        date_added=date_added,
        cover=cover,
        year="2025",
        track_number="1",
    )


TRACKS = (
    _t(
        "dnb01",
        "dnb",
        "Carrier Wave",
        "Loop Foundry",
        "Carrier Wave",
        "Drum & Bass",
        "174",
        "8A",
        316,
        "FLAC",
        0,
    ),
    _t(
        "dnb02",
        "dnb",
        "Night Drive",
        "Mira Kline, Halden",
        "Night Drive EP",
        "Drum & Bass",
        "172",
        "11B",
        292,
        "MP3",
        1,
    ),
    _t(
        "dnb03",
        "dnb",
        "Low Orbit",
        "Distant Objects",
        "Low Orbit",
        "Liquid",
        "174",
        "3A",
        310,
        "FLAC",
        2,
    ),
    _t(
        "dnb04",
        "dnb",
        "Feel This Pressure",
        "Kessel, Juno Park, Ada Vire",
        "Pressure Systems",
        "Drum & Bass",
        "173",
        "1A",
        304,
        "WAV",
        3,
    ),
    _t(
        "dnb05",
        "dnb",
        "Answer All My Signals (feat. Nia Brooke) [Extended Instrumental Mix]",
        "Peakform, Nitelane, LYNX, Sayra Dune",
        "Answer All My Signals (Remixes)",
        "Neurofunk",
        "175",
        "4A",
        328,
        "MP3",
        4,
        filename="answer_all_my_signals_extended",
    ),
    _t(
        "dnb06",
        "dnb",
        "Pump Line",
        "Peakform, Flava Dee",
        "Are We Awake?",
        "Jump Up",
        "174",
        "11A",
        339,
        "MP3",
        5,
    ),
    _t(
        "dnb07",
        "dnb",
        "Old Circuit",
        "Peakform, Badklaat",
        "Are We Awake?",
        "Jump Up",
        "174",
        "1A",
        305,
        "MP3",
        5,
    ),
    _t(
        "dnb08",
        "dnb",
        "Want It Back",
        "Peakform",
        "Are We Awake?",
        "Drum & Bass",
        "174",
        "9A",
        345,
        "FLAC",
        5,
    ),
    _t(
        "dnb09",
        "dnb",
        "Cannot Stop (Flux Version)",
        "Flux Harbor",
        "Cannot Stop",
        "",
        "174",
        "5A",
        304,
        "FLAC",
        6,
    ),
    _t(
        "dnb10",
        "dnb",
        "Star Cannon",
        "Skyreach",
        "Half Light",
        "Neurofunk",
        "176",
        "4A",
        329,
        "WAV",
        7,
    ),
    _t("dnb11", "dnb", "Rollers Only", "", "Unreleased", "Liquid", "172", "—", 287, "MP3", -1),
    _t(
        "dnb12",
        "dnb",
        "Deep Current",
        "Aster & Vale",
        "Tidal Works",
        "Liquid",
        "174",
        "6B",
        351,
        "FLAC",
        1,
    ),
    _t(
        "ukg01",
        "ukg",
        "Sunday Shuffle",
        "Coldharbour Tapes",
        "Sunday Shuffle",
        "UK Garage",
        "132",
        "10A",
        245,
        "MP3",
        3,
    ),
    _t(
        "ukg02",
        "ukg",
        "Two Step Theory",
        "Mae Holloway",
        "Theory EP",
        "UK Garage",
        "134",
        "7A",
        262,
        "FLAC",
        0,
    ),
    _t(
        "ukg03",
        "ukg",
        "Backroom Talk",
        "Rudi & The Late",
        "Backroom",
        "Speed Garage",
        "133",
        "2A",
        298,
        "MP3",
        6,
    ),
    _t(
        "ukg04",
        "ukg",
        "Late Bus Home",
        "Nightlines",
        "Late Bus Home",
        "UK Garage",
        "131",
        "12B",
        231,
        "WAV",
        2,
    ),
    _t(
        "ukg05",
        "ukg",
        "Soft Errors (Live at Le Sucre, Lyon)",
        "Aster & Vale",
        "Live Sessions",
        "UK Garage",
        "130",
        "5B",
        581,
        "FLAC",
        4,
    ),
    _t(
        "ukg06",
        "ukg",
        "Pirate Signal",
        "Tessa Kind",
        "Pirate Signal",
        "Bassline",
        "135",
        "8B",
        244,
        "MP3",
        7,
    ),
    _t(
        "dub01",
        "dubstep",
        "Weight Room",
        "Hollow Pines",
        "Weight Room",
        "Dubstep",
        "140",
        "1A",
        276,
        "FLAC",
        2,
    ),
    _t(
        "dub02",
        "dubstep",
        "Concrete Bloom",
        "Ostra",
        "Bloom",
        "Dubstep",
        "140",
        "6A",
        301,
        "MP3",
        5,
    ),
    _t(
        "dub03",
        "dubstep",
        "Half Step Ritual",
        "North Terminal",
        "Rituals",
        "Deep Dubstep",
        "140",
        "10B",
        334,
        "WAV",
        0,
    ),
    _t(
        "dub04",
        "dubstep",
        "Sub Pressure",
        "Kessel",
        "Sub Pressure",
        "Dubstep",
        "142",
        "9A",
        288,
        "MP3",
        3,
    ),
    _t(
        "dub05",
        "dubstep",
        "Glass Floor",
        "Wren Adler",
        "Glass Floor",
        "",
        "140",
        "—",
        256,
        "FLAC",
        -1,
    ),
    _t(
        "tec01",
        "techno",
        "Ritual Signal",
        "North Terminal",
        "Signals",
        "Techno",
        "130",
        "11A",
        412,
        "FLAC",
        4,
    ),
    _t(
        "tec02",
        "techno",
        "Warehouse Minutes",
        "Loop Foundry",
        "Minutes",
        "Techno",
        "132",
        "5A",
        389,
        "WAV",
        6,
    ),
    _t(
        "tec03",
        "techno",
        "Kontrollraum",
        "Jörg Neumann",
        "Kontrollraum",
        "Hard Techno",
        "145",
        "2B",
        356,
        "MP3",
        1,
    ),
    _t(
        "tec04",
        "techno",
        "Carrier Loop 04",
        "Loop Foundry",
        "Tools Vol. 2",
        "Techno",
        "134",
        "5A",
        432,
        "FLAC",
        7,
    ),
    _t(
        "tec05",
        "techno",
        "Nocturne pour machines",
        "Élise Marchand",
        "Nocturnes",
        "Hypnotic Techno",
        "128",
        "4B",
        468,
        "AIFF",
        2,
    ),
    _t(
        "smp01",
        "samples",
        "Untitled field recording 04",
        "",
        "",
        "Field recording",
        "—",
        "—",
        146,
        "WAV",
        -1,
        filename="04_été_ambiance",
    ),
    _t(
        "smp02",
        "samples",
        "Pluie sur la verrière",
        "Élise Marchand",
        "Carnet d'été",
        "Ambient",
        "—",
        "—",
        212,
        "WAV",
        -1,
    ),
    _t("smp03", "samples", "Cigales, 14 h", "", "Carnet d'été", "", "—", "—", 95, "WAV", -1),
    _t(
        "smp04",
        "samples",
        "Marché de Noailles",
        "Élise Marchand",
        "Carnet d'été",
        "Field recording",
        "—",
        "—",
        188,
        "FLAC",
        3,
    ),
)

PLAYLISTS = (
    DemoPlaylist("warmup", "Warm-up", ("ukg01", "ukg04", "dnb03", "dnb12", "tec05")),
    DemoPlaylist("peak", "Peak time", ("dnb05", "dnb06", "dnb07", "dnb10", "dub04", "tec03")),
    DemoPlaylist("rollers", "Sunday rollers", ("dnb03", "dnb11", "dnb12", "ukg02")),
    DemoPlaylist("check", "To check", ("dnb09", "dub05", "smp01")),
)

TASKS = (
    {
        "label": "Reading folder dnb",
        "detail": "12 of 18 files",
        "state": "running",
        "progress": 0.64,
    },
    {
        "label": "Converting 2 files to MP3",
        "detail": "Night Drive · 41%",
        "state": "running",
        "progress": 0.41,
    },
    {"label": "Reading folder ukg", "detail": "6 files", "state": "done", "progress": 1.0},
    {
        "label": "Reading folder Échantillons d'été",
        "detail": "One file could not be read. Retry after checking the disk.",
        "state": "error",
        "progress": 0.75,
    },
)

CONVERT_BATCHES = (
    {
        "label": "2 files → MP3 320 kbps",
        "detail": "In progress · 41%",
        "state": "running",
        "progress": 0.41,
    },
    {"label": "Peak time → AIFF", "detail": "Finished · 6 files", "state": "done", "progress": 1.0},
    {
        "label": "Warm-up → MP3 320 kbps",
        "detail": "Finished · 5 files",
        "state": "done",
        "progress": 1.0,
    },
)
