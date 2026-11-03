"""The DPAPI token store: a token round-trips, and the file never holds it in clear text."""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

import pytest
from mtee.plugins.remote import tokens  # pyright: ignore[reportMissingImports]
from mtee.plugins.remote.tokens import TokenError  # pyright: ignore[reportMissingImports]

needs_windows = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows only")


@needs_windows
def test_a_token_round_trips_and_is_deleted(tmp_path: Path) -> None:
    token = "dev_" + secrets.token_urlsafe(24)
    tokens.save_token(tmp_path, token)
    assert tokens.token_exists(tmp_path)
    assert tokens.load_token(tmp_path) == token

    replacement = "dev_" + secrets.token_urlsafe(24)
    tokens.save_token(tmp_path, replacement)
    assert tokens.load_token(tmp_path) == replacement

    tokens.delete_token(tmp_path)
    assert not tokens.token_exists(tmp_path)
    assert tokens.load_token(tmp_path) is None
    tokens.delete_token(tmp_path)  # nothing left to delete is not an error


@needs_windows
def test_the_file_does_not_hold_the_token_in_clear_text(tmp_path: Path) -> None:
    token = "dev_" + secrets.token_urlsafe(24)
    tokens.save_token(tmp_path, token)
    stored = (tmp_path / tokens.TOKEN_FILE).read_bytes()
    assert token.encode("utf-8") not in stored
    assert token[4:].encode("utf-8") not in stored
    # The write went through a temporary name, which is gone once the file is in place.
    assert sorted(path.name for path in tmp_path.iterdir()) == [tokens.TOKEN_FILE]


@needs_windows
def test_a_damaged_file_is_refused_with_a_sentence(tmp_path: Path) -> None:
    (tmp_path / tokens.TOKEN_FILE).write_bytes(b"not a protected blob")
    with pytest.raises(TokenError) as caught:
        tokens.load_token(tmp_path)
    assert "Connect again" in str(caught.value)


def test_other_systems_are_refused_with_a_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="needs Windows"):
        tokens.save_token(tmp_path, "dev_token")
    with pytest.raises(TokenError):
        tokens.load_token(tmp_path)
    assert issubclass(TokenError, RuntimeError)
