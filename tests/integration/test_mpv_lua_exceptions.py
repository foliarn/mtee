"""libmpv starts without its built-in Lua scripts, so no LuaJIT exception reaches faulthandler.

LuaJIT signals its errors with the SEH exception 0xE24C4A02, normally caught inside libmpv.
Python's faulthandler dumps every thread on each one, and dumping a thread that is running
Python code crashed the process intermittently with an access violation.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from mtee.services.mpv_backend import mpv_library_path

pytestmark = pytest.mark.native_audio

_PROBE = textwrap.dedent(
    """
    import faulthandler
    import time

    from mtee.services.mpv_backend import MpvBackend

    faulthandler.enable()
    # With the scripts loaded, about one lifetime in two raised the exception (measured on
    # 2026-10-14), so ten lifetimes make a silent pass of a regression unlikely.
    for _ in range(10):
        backend = MpvBackend(audio_output="null")
        time.sleep(0.3)
        backend.close()
    print("closed")
    """
)


def test_creating_the_backend_raises_no_luajit_exception() -> None:
    assert mpv_library_path().is_file()

    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert "0xe24c4a02" not in completed.stderr.lower()
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "closed"
