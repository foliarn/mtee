"""Initial genre vocabulary; free tags always begin empty."""

from __future__ import annotations

GENRE_TREE: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "House",
        (
            "Tech House",
            "Bass House",
            "Minimal House",
            "Deep House",
            "Disco House",
            "French House",
            "Afro House",
        ),
    ),
    ("Techno", ("Melodic Techno", "Hard Techno", "Dub Techno")),
    ("Garage", ("UK Garage", "Speed Garage", "2-Step")),
    ("Breaks", ("Jungle", "Drum & Bass", "Breakbeat")),
    ("Ambient", ("Downtempo", "Chillout")),
    ("Disco", ("Nu Disco",)),
    ("Trance", ("Progressive Trance",)),
    ("Hip-Hop", ()),
    ("Soul", ()),
    ("Funk", ()),
    ("Pop", ()),
)
