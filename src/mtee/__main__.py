"""Entry point used by ``python -m mtee`` and by the packaged MTEE.exe."""

from __future__ import annotations

import sys

from mtee.plugin_helper import dispatch
from mtee.services.wait_for_exit import strip_wait_option, wait_for_process_exit

if __name__ == "__main__":
    # A plugin helper process (plan 123.3) returns here, before the Qt application is imported.
    helper_code = dispatch(sys.argv)
    if helper_code is not None:
        sys.exit(helper_code)

    # A restarted MTEE waits until the old process has exited, so it reads the saved layout and
    # settings. After the timeout it starts anyway (plan 123.6). The option never reaches argparse.
    argv, old_pid = strip_wait_option(sys.argv)
    if old_pid is not None:
        wait_for_process_exit(old_pid)

    from mtee.app import main

    sys.exit(main(argv))
