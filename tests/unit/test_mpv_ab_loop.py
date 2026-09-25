from __future__ import annotations

from mtee.services.mpv_backend import MpvBackend


def test_mpv_ab_loop_uses_native_set_property_commands(monkeypatch) -> None:
    backend = object.__new__(MpvBackend)
    commands: list[tuple[str, ...]] = []

    def record(*arguments: str, required: bool = True) -> None:
        assert required
        commands.append(arguments)

    monkeypatch.setattr(backend, "_command", record)
    backend.set_ab_loop(1_250_000, 2_500_000)
    backend.set_ab_loop(None, None)

    assert commands == [
        ("set", "ab-loop-a", "1.250000"),
        ("set", "ab-loop-b", "2.500000"),
        ("set", "ab-loop-a", "no"),
        ("set", "ab-loop-b", "no"),
    ]
