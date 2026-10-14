"""Core artist index: built off the graphical thread, shared by the Artists view and the tag editor.

The service keeps the last finished index and the user's overrides. ``refresh`` asks for a
new index; a request made while one is being built marks it stale, so one more build runs
when it ends. Only the graphical thread reads or changes this object. The tag editor uses it
as its ``ArtistCreditRules``: it splits typed credits with the same rules and records the
"One artist" / "Several artists" answers in the same store.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal

from mtee.domain.artist_index import (
    MODE_ONE_ARTIST,
    MODE_SPLIT,
    ArtistEntry,
    ArtistIndex,
    build_artist_index,
    has_separator,
    split_artist_credit,
)
from mtee.domain.artists import clean_name, normalize_key
from mtee.persistence.credit_override_repository import CreditOverrideRepository
from mtee.persistence.library_repository import LibraryRepository
from mtee.services.jobs import JobContext, JobService

__all__ = ["ArtistIndexService"]


class ArtistIndexService(QObject):
    """Owns the artist index of the library and the credit overrides."""

    indexChanged = Signal()  # noqa: N815 - Qt signal name, read from QML
    _built = Signal(object, int)

    def __init__(
        self,
        library: LibraryRepository,
        overrides: CreditOverrideRepository,
        jobs: JobService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._library = library
        self._store = overrides
        self._jobs = jobs
        self._index = ArtistIndex()
        self._overrides: dict[str, tuple[str, str]] = overrides.modes()
        self._generation = 0
        self._running = False
        self._last_error = ""
        self._built.connect(self._on_built)

    # ------------------------------------------------------------------ index

    @property
    def index(self) -> ArtistIndex:
        return self._index

    @property
    def last_error(self) -> str:
        """The message of the last failed build; empty after a successful one."""
        return self._last_error

    def artists(self) -> list[ArtistEntry]:
        return list(self._index.artists)

    def tracks_of(self, key: str) -> list[str]:
        return list(self._index.tracks_by_artist.get(key, ()))

    def refresh(self) -> None:
        """Ask for an index that matches the library and the overrides as they are now."""
        self._generation += 1
        if not self._running:
            self._start()

    def _start(self) -> None:
        generation = self._generation
        self._running = True

        def build(_context: JobContext) -> None:
            try:
                index = build_artist_index(self._library.artist_credit_rows(), self._store.modes())
            except Exception as error:
                self._built.emit(str(error) or type(error).__name__, generation)
                return
            self._built.emit(index, generation)

        try:
            self._jobs.submit(build, label="Index artists", visible=False)
        except RuntimeError:
            self._running = False  # the application is shutting down

    def _on_built(self, result: object, generation: int) -> None:
        self._running = False
        if generation != self._generation:
            self._start()
            return
        if isinstance(result, ArtistIndex):
            self._index = result
            self._last_error = ""
            self.indexChanged.emit()
        else:
            self._last_error = str(result)

    # ------------------------------------------------------------------ overrides

    def _rule_inputs(self) -> tuple[list[str], set[str]]:
        one_names = [text for text, mode in self._overrides.values() if mode == MODE_ONE_ARTIST]
        split_keys = {key for key, (_text, mode) in self._overrides.items() if mode == MODE_SPLIT}
        return one_names, split_keys

    def overrides(self) -> list[dict[str, str]]:
        """Every choice made by the user, as ``{"key", "text", "mode"}``, sorted by text."""
        return sorted(
            (
                {"key": key, "text": text, "mode": mode}
                for key, (text, mode) in self._overrides.items()
            ),
            key=lambda item: item["text"].casefold(),
        )

    def remove_override(self, credit_key: str) -> bool:
        """Forget a choice; the next index build cuts that credit by the default rules."""
        key = normalize_key(credit_key)
        removed = self._store.remove(key)
        self._overrides.pop(key, None)
        if removed:
            self.refresh()
        return removed

    def record_credit_choice(self, text: str, *, one_artist: bool) -> None:
        """Keep a credit whole ("This is one artist") or always cut it."""
        self._record([text], one_artist=one_artist)

    def _record(self, texts: list[str], *, one_artist: bool) -> int:
        mode = MODE_ONE_ARTIST if one_artist else MODE_SPLIT
        written = 0
        for text in texts:
            cleaned = clean_name(text)
            if not cleaned:
                continue
            self._store.set_mode(cleaned, mode)
            self._overrides[normalize_key(cleaned)] = (cleaned, mode)
            written += 1
        if written:
            self.refresh()
        return written

    def one_artist_credits(self, key: str) -> list[str]:
        """Credit texts that "This is one artist" would keep whole for the artist ``key``."""
        return self._index.one_artist_credits(key)

    def split_credits(self, key: str) -> list[str]:
        """Credit texts that "Split into separate artists" would cut for the artist ``key``."""
        return self._index.split_credits(key)

    def make_one_artist(self, key: str) -> int:
        """Apply "This is one artist" to the credits of ``key``; return how many were kept."""
        return self._record(self.one_artist_credits(key), one_artist=True)

    def split_artist(self, key: str) -> int:
        """Apply "Split into separate artists" to the credits of ``key``."""
        return self._record(self.split_credits(key), one_artist=False)

    # ------------------------------------------------------------------ ArtistCreditRules

    def split(self, text: str) -> list[str]:
        """The artists a typed or tagged credit gives under the rules and the overrides."""
        one_names, split_keys = self._rule_inputs()
        return split_artist_credit(
            text,
            solo=self._index.solo_keys,
            one_names=one_names,
            split_keys=split_keys,
        )

    def needs_choice(self, text: str) -> bool:
        """Whether a typed credit holds a separator that the user has not answered yet."""
        cleaned = clean_name(text)
        return has_separator(cleaned) and normalize_key(cleaned) not in self._overrides

    def suggestions(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Known artists whose name contains ``query``, as ``{"id", "name"}``."""
        needle = normalize_key(query)
        if not needle:
            return []
        found = [
            {"id": artist.key, "name": artist.name}
            for artist in self._index.artists
            if needle in artist.key
        ]
        return found[:limit]
