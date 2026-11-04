"""The settings file and the rule of each field."""

from __future__ import annotations

from pathlib import Path

from mtee_remote_admin.envfile import FIELD_BY_KEY, EnvFile, problems


def test_a_change_keeps_the_comments_the_order_and_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "server.env"
    path.write_text("# The port.\nPORT=8080\nOTHER=kept # a note\n\nBIND_ADDRESS=127.0.0.1\n")
    env = EnvFile.read(path)
    assert env.values() == {"PORT": "8080", "OTHER": "kept", "BIND_ADDRESS": "127.0.0.1"}

    env.set("PORT", "9000")
    env.set("MUSIC_DIR", "/srv/my music")
    env.write(path)

    assert path.read_text().splitlines() == [
        "# The port.",
        "PORT=9000",
        "OTHER=kept # a note",
        "",
        "BIND_ADDRESS=127.0.0.1",
        'MUSIC_DIR="/srv/my music"',
    ]
    assert EnvFile.read(path).get("MUSIC_DIR") == "/srv/my music"
    assert path.stat().st_mode & 0o777 == 0o600, "it can hold addresses and names: owner only"


def test_quotes_survive_a_round_trip(tmp_path: Path) -> None:
    env = EnvFile()
    env.set("PUBLIC_URL", 'say "hi" \\ there')
    env.write(tmp_path / "e")
    assert EnvFile.read(tmp_path / "e").get("PUBLIC_URL") == 'say "hi" \\ there'


def test_each_field_refuses_what_the_server_would(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    good = {
        "ADMIN_USER": "ana",
        "MUSIC_DIR": str(music),
        "DATA_DIR": str(tmp_path / "data"),
        "PORT": "8080",
        "BIND_ADDRESS": "192.168.1.29",
        "PUBLIC_URL": "https://music.example.net",
        "TRUSTED_PROXIES": "172.18.0.0/16, 127.0.0.1",
        "SCAN_INTERVAL": "3600",
        "UID": "1000",
        "GID": "1000",
        "PROXY_NETWORK": "",
    }
    assert problems(good) == {}
    bad = {
        **good,
        "ADMIN_USER": "A",
        "MUSIC_DIR": str(tmp_path / "missing"),
        "DATA_DIR": "relative/data",
        "PORT": "70000",
        "BIND_ADDRESS": "0.0.0.0",
        "PUBLIC_URL": "music.example.net",
        "TRUSTED_PROXIES": "proxy",
        "SCAN_INTERVAL": "-1",
    }
    assert set(problems(bad)) == {
        "ADMIN_USER",
        "MUSIC_DIR",
        "DATA_DIR",
        "PORT",
        "BIND_ADDRESS",
        "PUBLIC_URL",
        "TRUSTED_PROXIES",
        "SCAN_INTERVAL",
    }
    assert "0.0.0.0" in problems(bad)["BIND_ADDRESS"]
    assert FIELD_BY_KEY["BIND_ADDRESS"].check("8.8.8.8") is not None, "never a public address"


def test_a_home_network_address_warns_about_plain_http() -> None:
    field = FIELD_BY_KEY["BIND_ADDRESS"]
    assert field.warning("127.0.0.1") is None
    warning = field.warning("192.168.1.29")
    assert warning is not None and "unencrypted" in warning
