"""Measure live QML responsiveness while indexing a synthetic audio library."""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import time
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QTimer

from mtee.app import _build_runtime, _shutdown, create_application
from mtee.cli import AppOptions
from mtee.models.workspace_model import WorkspaceModel


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _working_set_bytes() -> int | None:
    try:
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.restype = wintypes.HANDLE
        get_current_process.argtypes = []
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.restype = wintypes.BOOL
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        result = get_process_memory_info(get_current_process(), ctypes.byref(counters), counters.cb)
        return int(counters.WorkingSetSize) if result else None
    except (AttributeError, OSError):
        return None


def measure(root: Path, data_dir: Path) -> dict[str, object]:
    application = create_application(["mtee"])
    runtime = _build_runtime(application, AppOptions(data_dir=data_dir))
    if runtime is None or not isinstance(runtime.workspace, WorkspaceModel):
        raise RuntimeError("The live QML window did not load.")
    workspace = runtime.workspace
    delays_ms: list[float] = []
    first_batch_ms: float | None = None
    start = time.perf_counter()
    baseline_bytes = _working_set_bytes()
    peak_bytes = baseline_bytes
    previous_tick = time.perf_counter()
    requested_id = workspace.addRoot(str(root))
    if not requested_id:
        _shutdown(runtime)
        raise RuntimeError("The fixture root could not be added.")
    root_id = requested_id

    def sample_event_loop() -> None:
        nonlocal previous_tick, peak_bytes, first_batch_ms
        now = time.perf_counter()
        delays_ms.append(max(0.0, (now - previous_tick) * 1000 - 10))
        previous_tick = now
        count = workspace._scan_counts.get(root_id, 0)
        if count and first_batch_ms is None:
            first_batch_ms = (now - start) * 1000
        working_set = _working_set_bytes()
        if working_set is not None:
            peak_bytes = max(peak_bytes or 0, working_set)

    sampler = QTimer()
    sampler.setInterval(10)
    sampler.timeout.connect(sample_event_loop)
    sampler.start()

    watcher = QTimer()
    watcher.setInterval(25)

    def finish_when_scans_end() -> None:
        if root_id not in workspace._requests and runtime.jobs.active_count() == 0:
            application.quit()

    watcher.timeout.connect(finish_when_scans_end)
    watcher.start()
    application.exec()
    elapsed_ms = (time.perf_counter() - start) * 1000
    sampler.stop()
    watcher.stop()
    row = (
        runtime.database.connection()
        .execute("SELECT COUNT(*) FROM root_tracks WHERE root_id=? AND present=1", (root_id,))
        .fetchone()
    )
    count = int(row[0]) if row else 0
    delays_ms.sort()
    percentile_index = max(0, math.ceil(0.95 * len(delays_ms)) - 1)
    p95_delay_ms = delays_ms[percentile_index] if delays_ms else 0.0
    result = {
        "root": str(root.resolve()),
        "tracks_indexed": count,
        "time_to_first_batch_ms": round(first_batch_ms, 1) if first_batch_ms is not None else None,
        "scan_total_ms": round(elapsed_ms, 1),
        "event_loop_delay_p95_ms": round(p95_delay_ms, 2),
        "event_loop_delay_max_ms": round(max(delays_ms, default=0.0), 2),
        "working_set_baseline_mib": round((baseline_bytes or 0) / (1024 * 1024), 1),
        "working_set_peak_mib": round((peak_bytes or 0) / (1024 * 1024), 1),
        "working_set_growth_mib": round(
            ((peak_bytes or 0) - (baseline_bytes or 0)) / (1024 * 1024), 1
        ),
    }
    _shutdown(runtime)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    arguments = parser.parse_args(argv)
    print(json.dumps(measure(arguments.root, arguments.data_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
