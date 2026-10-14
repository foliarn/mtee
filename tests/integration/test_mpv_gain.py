"""The gain property of the bundled libmpv: set, read back, and kept inside its range."""

from __future__ import annotations

import pytest

from mtee.domain.loudness import GAIN_LIMITS_DB
from mtee.services.mpv_backend import MpvBackend
from mtee.services.player_backend import PlayerBackendError


@pytest.fixture(scope="module")
def backend():
    # One native player for the module: each create/close cycle of libmpv is a chance for
    # the pre-existing shutdown race of MpvBackend (see the plan 116 record), so it is kept low.
    try:
        native = MpvBackend()
    except PlayerBackendError as error:
        pytest.skip(f"The bundled libmpv runtime is unavailable: {error}")
    yield native
    native.close()


def test_the_gain_is_set_and_read_back_from_libmpv(backend: MpvBackend) -> None:
    backend.set_gain_db(-6.0)
    assert backend.gain_db() == pytest.approx(-6.0)

    backend.set_gain_db(0.0)
    assert backend.gain_db() == pytest.approx(0.0)


def test_a_boost_above_libmpv_default_of_12_db_is_accepted(backend: MpvBackend) -> None:
    # libmpv refuses +30 dB unless volume-gain-max is raised; the backend raises it.
    backend.set_gain_db(30.0)

    assert backend.gain_db() == pytest.approx(30.0)


def test_out_of_range_gains_are_clamped_to_the_documented_limits(backend: MpvBackend) -> None:
    low, high = GAIN_LIMITS_DB

    backend.set_gain_db(500.0)
    assert backend.gain_db() == pytest.approx(high)

    backend.set_gain_db(-500.0)
    assert backend.gain_db() == pytest.approx(low)
