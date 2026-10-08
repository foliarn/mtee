from pathlib import Path

import pytest

from mtee.domain.genres import GenreError
from mtee.services.genre_seed_service import GenreSeedService, protect_destination


@pytest.mark.parametrize(
    "rules",
    [
        [{"folder": "house", "scope": "exact"}, {"folder": "house", "scope": "exact"}],
        [{"folder": "house", "scope": "guess"}],
        [{"folder": "../house", "scope": "exact"}],
        [{"folder": "house", "scope": "exact", "genres": ["unknown"]}],
        [{"folder": "house", "scope": "exact", "rule": "metadata_bpm"}],
    ],
)
def test_invalid_mapping_is_refused(tmp_path: Path, rules: list[dict]) -> None:
    with pytest.raises(GenreError):
        GenreSeedService(tmp_path / "unused.sqlite3", mapping={"version": 1, "rules": rules})


def test_protected_paths_cannot_receive_reports_or_backups(tmp_path: Path) -> None:
    music = tmp_path / "music"
    with pytest.raises(GenreError):
        protect_destination(music / "sub" / "backup.sqlite3", [str(music)])
    with pytest.raises(GenreError):
        protect_destination(music / "sub" / ".." / "report", [str(music)])
    protect_destination(tmp_path / "music-other" / "backup.sqlite3", [str(music)])
