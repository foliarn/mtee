"""What the first-match dialog reads and calls: a ``QObject`` over the last match report.

The rows are built here, as plain maps, so the dialog only draws them. Each group keeps its first
``ROW_LIMIT`` rows and says how many more there are. Graphical thread only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from ..matcher import DUPLICATE, UNREADABLE, MatchResult

if TYPE_CHECKING:
    from ..first_match import MatchReport

ROW_LIMIT = 200
# The global choice for the "Tags differ" group. The first one is the default at each report.
CHOICES: tuple[str, ...] = ("computer", "server", "later")

_GROUPS: tuple[tuple[str, str], ...] = (
    ("matched", "Matched"),
    ("to_upload", "To upload"),
    ("server_only", "Server only"),
    ("tags_differ", "Same audio, different file"),
    ("not_matched", "Not matched"),
)
_GROUP_TEXT = {
    "matched": "The same audio on both sides. They are linked and need no transfer.",
    "to_upload": "Only on this computer. They are sent to the server.",
    "server_only": "Only on the server. They show as Server only until you download them.",
    "tags_differ": "The same audio on both sides, with different tags, names or folders.",
    "not_matched": "Left out of the sync: a file MTEE cannot read, or a second copy of a track "
    "already matched.",
}
_TONE = {"tags_differ": "warning", "not_matched": "secondary"}
_REASON = {UNREADABLE: "Cannot be read", DUPLICATE: "A second copy of a track already matched"}
FOOTER = (
    "Nothing moves before you press Start sync. You can run the match again from Settings > Remote."
)


def intro_text(report: MatchReport) -> str:
    return (
        f"This computer has {report.local_total:,} tracks and the server {report.server_total:,}. "
        "MTEE compared them by their audio, not by file name or tags. "
        "Nothing is sent or downloaded until you press Start sync."
    )


def group_rows(result: MatchResult, opened: Callable[[str], bool]) -> list[dict[str, Any]]:
    """The five groups of the summary, each with its count, its first rows and its open state."""
    rows_of = {
        "matched": [
            _row(
                pair.local.relative_path,
                _server_note(pair.local.relative_path, pair.server.relative_path),
            )
            for pair in result.matched
        ],
        "to_upload": [_row(local.relative_path, "") for local in result.to_upload],
        "server_only": [_row(item.relative_path, "") for item in result.server_only],
        "tags_differ": [
            _row(
                pair.local.relative_path,
                _server_note(pair.local.relative_path, pair.server.relative_path),
            )
            for pair in result.tags_differ
        ],
        "not_matched": [
            _row(entry.local.relative_path, _REASON.get(entry.reason, entry.reason))
            for entry in result.not_matched
        ],
    }
    counts = result.counts
    groups: list[dict[str, Any]] = []
    for key, label in _GROUPS:
        rows = rows_of[key]
        groups.append(
            {
                "key": key,
                "label": label,
                "text": _GROUP_TEXT[key],
                "count": f"{counts[key]:,}",
                "tone": _TONE.get(key, "neutral"),
                "open": opened(key),
                "choose": key == "tags_differ",
                "items": rows[:ROW_LIMIT],
                "more": max(0, len(rows) - ROW_LIMIT),
            }
        )
    return groups


def _row(name: str, note: str) -> dict[str, str]:
    return {"name": name, "note": note}


def _other_path(local: str, server: str) -> str:
    """The server's path when it differs from the local one, else an empty string."""
    return server if server != local else ""


def _server_note(local: str, server: str) -> str:
    """The second line of a row: where the server keeps the track, when that is not here."""
    other = _other_path(local, server)
    return f"On the server: {other}" if other else ""


class FirstMatchBackend(QObject):
    """The backend of ``ui/first_match.qml``: the report of the last match, the choice for
    "Tags differ", and two actions."""

    changed = Signal()
    # Its own signal: a new choice must not rebuild the groups, or the scroll position is lost.
    choiceChanged = Signal()  # noqa: N815

    def __init__(self) -> None:
        super().__init__()
        self._report: MatchReport | None = None
        self._ref = ""
        self._open: dict[str, bool] = {}
        self._choice = CHOICES[0]
        self._start: Callable[[MatchReport], None] | None = None

    def bind(self, start: Callable[[MatchReport], None]) -> None:
        """Set the function that runs Start sync for a report."""
        self._start = start

    @property
    def report(self) -> MatchReport | None:
        return self._report

    @property
    def ref(self) -> str:
        return self._ref

    def show(self, report: MatchReport, ref: str) -> None:
        """Show a new report; the groups with rows open as they are, tags differ open first.

        Each report starts again with the default choice: a choice made for one report does not
        carry over to the next.
        """
        self._report = report
        self._ref = ref
        self._open = {}
        self._choice = CHOICES[0]
        self.choiceChanged.emit()
        self.changed.emit()

    def _is_open(self, key: str) -> bool:
        if key in self._open:
            return self._open[key]
        if key == "tags_differ" and self._report is not None:
            return self._report.result.counts["tags_differ"] > 0
        return False

    @Property(bool, notify=changed)
    def hasReport(self) -> bool:  # noqa: N802
        return self._report is not None

    @Property(str, notify=changed)
    def intro(self) -> str:
        return intro_text(self._report) if self._report is not None else ""

    @Property(str, constant=True)
    def footer(self) -> str:
        return FOOTER

    @Property(list, notify=changed)
    def groups(self) -> list[dict[str, Any]]:
        if self._report is None:
            return []
        return group_rows(self._report.result, self._is_open)

    @Property(str, notify=choiceChanged)
    def choice(self) -> str:
        """The global choice for "Tags differ": "computer", "server" or "later"."""
        return self._choice

    def current_choice(self) -> str:
        """The same choice, for Python callers (the controller reads it at Start sync)."""
        return self._choice

    @Slot(str)
    def toggle(self, key: str) -> None:
        self._open[key] = not self._is_open(key)
        self.changed.emit()

    @Slot(str)
    def setChoice(self, key: str) -> None:  # noqa: N802
        """Choose the side for "Tags differ"; a key that is not a choice is ignored."""
        if key not in CHOICES or key == self._choice:
            return
        self._choice = key
        self.choiceChanged.emit()

    @Slot()
    def startSync(self) -> None:  # noqa: N802
        report = self._report
        self._report = None
        self.changed.emit()
        if report is not None and self._start is not None:
            self._start(report)

    @Slot()
    def discard(self) -> None:
        """Cancel: forget the report. Nothing has been written."""
        self._report = None
        self.changed.emit()
