from mtee.domain.playlists import musical_identity


def test_formats_paths_case_accents_and_artist_order_do_not_define_a_song() -> None:
    first = {"title": "Écho (Original Mix)", "artist": "Álice, Bob", "format": "FLAC"}
    second = {"title": "echo (original mix)", "artist": "bob, alice", "format": "MP3"}
    assert musical_identity(first) == musical_identity(second)
    assert musical_identity(first) != musical_identity(first | {"title": "Écho (Live)"})
    assert musical_identity(first) != musical_identity(first | {"title": "Écho (Bob Remix)"})
    assert musical_identity(first | {"artist": ""}) is None
    assert musical_identity(first | {"identityUncertain": True}) is None
