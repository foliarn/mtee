"""The small dialogs of the TUI: a question, a text, a new password."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

MIN_PASSWORD = 8


class ConfirmScreen(ModalScreen[bool]):
    """A yes or no question; `danger` draws the yes button in the error colour."""

    def __init__(self, question: str, yes: str = "Yes", *, danger: bool = False) -> None:
        super().__init__()
        self._question = question
        self._yes = yes
        self._danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self._question, classes="question")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="no")
                yield Button(self._yes, id="yes", variant="error" if self._danger else "primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def key_escape(self) -> None:
        self.dismiss(False)


class TextScreen(ModalScreen[str | None]):
    """One line of text; None when cancelled."""

    def __init__(self, question: str, value: str = "", placeholder: str = "") -> None:
        super().__init__()
        self._question = question
        self._value = value
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._question, classes="question")
            yield Input(self._value, placeholder=self._placeholder, id="text")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="no")
                yield Button("OK", id="yes", variant="primary")

    def on_input_submitted(self) -> None:
        self.dismiss(self.query_one("#text", Input).value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self.query_one("#text", Input).value if event.button.id == "yes" else None)

    def key_escape(self) -> None:
        self.dismiss(None)


class PasswordScreen(ModalScreen[str | None]):
    """A new password, typed twice; None when cancelled. It is never shown or kept."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._title, classes="question")
            yield Input(password=True, placeholder="New password", id="first")
            yield Input(password=True, placeholder="The same again", id="second")
            yield Static("", id="problem", classes="problem")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="no")
                yield Button("Set password", id="yes", variant="primary")

    def _submit(self) -> None:
        first = self.query_one("#first", Input).value
        second = self.query_one("#second", Input).value
        problem = check_password(first, second)
        if problem:
            self.query_one("#problem", Static).update(problem)
            return
        self.dismiss(first)

    def on_input_submitted(self) -> None:
        self._submit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "yes":
            self._submit()
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


def check_password(first: str, second: str) -> str:
    """The sentence that refuses a new password, or "" (the server checks it again)."""
    if len(first) < MIN_PASSWORD:
        return f"At least {MIN_PASSWORD} characters."
    if first != second:
        return "The two passwords differ."
    if "\n" in first or "\r" in first:
        return "A password is one line."
    return ""
