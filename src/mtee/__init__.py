"""MTEE — Music Tagging and Editing Explorer."""

from __future__ import annotations

import os

# OpenBLAS (numpy's linear algebra) commits a buffer per CPU core when numpy is imported: about
# 490 MB on a 16-thread machine, measured on 2026-11-03. MTEE's own products are small and run in
# job threads, so one BLAS thread costs no speed. Set before any MTEE module imports numpy.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

__all__ = ["__version__"]

__version__ = "0.3.0"
