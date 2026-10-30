"""Entry point used by ``python -m mtee`` and by the packaged MTEE.exe."""

from __future__ import annotations

import sys

from mtee.plugin_helper import dispatch

if __name__ == "__main__":
    # A plugin helper process (plan 123.3) returns here, before the Qt application is imported.
    helper_code = dispatch(sys.argv)
    if helper_code is not None:
        sys.exit(helper_code)

    from mtee.app import main

    sys.exit(main(sys.argv))
