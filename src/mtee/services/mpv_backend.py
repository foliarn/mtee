"""Audio-only ctypes adapter for the version-pinned Windows libmpv runtime."""

from __future__ import annotations

import ctypes
import os
import struct
import sys
import threading
from pathlib import Path
from typing import Any

from mtee.services.player_backend import BackendEvent, BackendEventHandler, PlayerBackendError

__all__ = ["MpvBackend", "mpv_library_path"]

_MPV_FORMAT_STRING = 1
_MPV_FORMAT_FLAG = 3
_MPV_FORMAT_INT64 = 4
_MPV_FORMAT_DOUBLE = 5
_MPV_EVENT_SHUTDOWN = 1
_MPV_EVENT_START_FILE = 6
_MPV_EVENT_END_FILE = 7
_MPV_EVENT_FILE_LOADED = 8
_MPV_EVENT_PROPERTY_CHANGE = 22
_MPV_END_FILE_EOF = 0
_MPV_END_FILE_ERROR = 4


class _MpvEvent(ctypes.Structure):
    _fields_ = [
        ("event_id", ctypes.c_int),
        ("error", ctypes.c_int),
        ("reply_userdata", ctypes.c_ulonglong),
        ("data", ctypes.c_void_p),
    ]


class _MpvEventProperty(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_char_p),
        ("format", ctypes.c_int),
        ("data", ctypes.c_void_p),
    ]


class _MpvEventEndFile(ctypes.Structure):
    _fields_ = [
        ("reason", ctypes.c_int),
        ("error", ctypes.c_int),
        ("playlist_entry_id", ctypes.c_longlong),
        ("playlist_insert_id", ctypes.c_longlong),
        ("playlist_insert_num_entries", ctypes.c_int),
    ]


_PROPERTY_FORMATS = {
    "duration": _MPV_FORMAT_DOUBLE,
    "pause": _MPV_FORMAT_FLAG,
    "seekable": _MPV_FORMAT_FLAG,
    "audio-codec-name": _MPV_FORMAT_STRING,
    "audio-samplerate": _MPV_FORMAT_INT64,
    "audio-channels": _MPV_FORMAT_STRING,
}


def mpv_library_path() -> Path:
    """Return the controlled bundled path, or the developer vendor path."""
    if getattr(sys, "frozen", False):
        root = Path(vars(sys)["_MEIPASS"])
        return root / "mtee" / "native" / "mpv" / "libmpv-2.dll"
    project_root = Path(__file__).resolve().parents[3]
    return project_root / "vendor" / "mpv" / "libmpv-2.dll"


class MpvBackend:
    """One libmpv player, with its event queue copied from a worker thread."""

    def __init__(
        self,
        library_path: Path | None = None,
        *,
        audio_output: str = "wasapi",
        wait_timeout_seconds: float = 0.1,
    ) -> None:
        if struct.calcsize("P") != 8:
            raise PlayerBackendError("The bundled libmpv runtime requires 64-bit Python.")
        path = library_path or mpv_library_path()
        if not path.is_file():
            raise PlayerBackendError(f"The bundled libmpv runtime is missing: {path}")

        self._dll_directory: Any = None
        if os.name == "nt" and hasattr(os, "add_dll_directory"):
            # Keep this handle alive for the lifetime of libmpv. Its optional Vulkan
            # loader can then be resolved from the normal Windows driver installation.
            self._dll_directory = os.add_dll_directory(str(path.parent))
        try:
            self._lib = ctypes.CDLL(str(path))
        except OSError as error:
            if self._dll_directory is not None:
                self._dll_directory.close()
                self._dll_directory = None
            raise PlayerBackendError(f"Could not load libmpv from {path}: {error}") from error

        self._bind_functions()
        self._ctx = self._lib.mpv_create()
        if not self._ctx:
            self._release_dll_directory()
            raise PlayerBackendError("libmpv could not create a player instance.")
        self._handler: BackendEventHandler | None = None
        self._handler_lock = threading.Lock()
        self._session_lock = threading.Lock()
        self._active_session_id = 0
        self._pending_session_id = 0
        self._wait_timeout_seconds = wait_timeout_seconds
        self._closing = threading.Event()
        self._initialized = False

        options = {
            "config": "no",
            "load-scripts": "no",
            "idle": "yes",
            "terminal": "no",
            "input-default-bindings": "no",
            "input-vo-keyboard": "no",
            "vo": "null",
            "vid": "no",
            "audio-display": "no",
            "ao": audio_output,
            "audio-client-name": "MTEE",
            "sub-auto": "no",
        }
        try:
            for name, value in options.items():
                self._check(
                    self._lib.mpv_set_option_string(
                        self._ctx, name.encode("utf-8"), value.encode("utf-8")
                    ),
                    f"set option {name}",
                )
            self._check(self._lib.mpv_initialize(self._ctx), "initialize")
            self._initialized = True
            for name, value_format in _PROPERTY_FORMATS.items():
                result = self._lib.mpv_observe_property(
                    self._ctx, 0, name.encode("ascii"), value_format
                )
                self._check(result, f"observe {name}")
        except Exception:
            self._lib.mpv_terminate_destroy(self._ctx)
            self._ctx = None
            self._release_dll_directory()
            raise

        self._event_thread = threading.Thread(
            target=self._event_loop, name="mtee-libmpv-events", daemon=True
        )
        self._event_thread.start()

    def set_event_handler(self, handler: BackendEventHandler | None) -> None:
        with self._handler_lock:
            self._handler = handler

    def load(self, path: Path, session_id: int) -> None:
        if self._closing.is_set() or not self._ctx:
            raise PlayerBackendError("The libmpv backend is closed.")
        with self._session_lock:
            self._pending_session_id = session_id
        self._command("loadfile", str(path), "replace")

    def set_paused(self, paused: bool) -> None:
        self._set_property("pause", _MPV_FORMAT_FLAG, ctypes.c_int(bool(paused)))

    def seek(self, position_us: int) -> None:
        seconds = max(0, int(position_us)) / 1_000_000
        self._command("seek", format(seconds, ".6f"), "absolute+exact")

    def set_ab_loop(self, start_us: int | None, end_us: int | None) -> None:
        self._command(
            "set", "ab-loop-a", "no" if start_us is None else format(start_us / 1_000_000, ".6f")
        )
        self._command(
            "set", "ab-loop-b", "no" if end_us is None else format(end_us / 1_000_000, ".6f")
        )

    def set_volume(self, value: int) -> None:
        self._set_property("volume", _MPV_FORMAT_DOUBLE, ctypes.c_double(max(0, min(100, value))))

    def position_us(self) -> int | None:
        value = ctypes.c_double()
        result = self._lib.mpv_get_property(
            self._ctx, b"time-pos", _MPV_FORMAT_DOUBLE, ctypes.byref(value)
        )
        return self._seconds_to_us(value.value) if result >= 0 else None

    def stop(self) -> None:
        if self._ctx and not self._closing.is_set():
            self._command("stop")

    def close(self) -> None:
        if self._closing.is_set():
            return
        self.set_event_handler(None)
        self._closing.set()
        if self._ctx:
            self._command("quit", required=False)
            self._lib.mpv_wakeup(self._ctx)
        if self._event_thread.is_alive():
            self._event_thread.join(timeout=2.0)
        if self._event_thread.is_alive():
            # The event loop still dereferences both the context and the DLL.
            # Retain them rather than freeing native state under a live thread.
            raise PlayerBackendError("The libmpv event thread did not stop before shutdown.")
        if self._ctx:
            self._lib.mpv_terminate_destroy(self._ctx)
            self._ctx = None
        self._release_dll_directory()

    def _bind_functions(self) -> None:
        lib = self._lib
        lib.mpv_create.restype = ctypes.c_void_p
        lib.mpv_create.argtypes = []
        lib.mpv_set_option_string.restype = ctypes.c_int
        lib.mpv_set_option_string.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        lib.mpv_initialize.restype = ctypes.c_int
        lib.mpv_initialize.argtypes = [ctypes.c_void_p]
        lib.mpv_observe_property.restype = ctypes.c_int
        lib.mpv_observe_property.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulonglong,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        lib.mpv_command.restype = ctypes.c_int
        lib.mpv_command.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p)]
        lib.mpv_set_property.restype = ctypes.c_int
        lib.mpv_set_property.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        lib.mpv_get_property.restype = ctypes.c_int
        lib.mpv_get_property.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        lib.mpv_wait_event.restype = ctypes.POINTER(_MpvEvent)
        lib.mpv_wait_event.argtypes = [ctypes.c_void_p, ctypes.c_double]
        lib.mpv_wakeup.restype = None
        lib.mpv_wakeup.argtypes = [ctypes.c_void_p]
        lib.mpv_terminate_destroy.restype = None
        lib.mpv_terminate_destroy.argtypes = [ctypes.c_void_p]
        lib.mpv_error_string.restype = ctypes.c_char_p
        lib.mpv_error_string.argtypes = [ctypes.c_int]

    def _event_loop(self) -> None:
        while not self._closing.is_set():
            event_pointer = self._lib.mpv_wait_event(self._ctx, self._wait_timeout_seconds)
            if not event_pointer:
                continue
            event = event_pointer.contents
            if event.event_id == _MPV_EVENT_SHUTDOWN:
                break
            if event.event_id == _MPV_EVENT_START_FILE:
                with self._session_lock:
                    self._active_session_id = self._pending_session_id
                self._emit("start-file", self._active_session_id)
            elif event.event_id == _MPV_EVENT_FILE_LOADED:
                self._emit("loaded", self._active_session_id)
            elif event.event_id == _MPV_EVENT_END_FILE:
                self._handle_end_file(event.data)
            elif event.event_id == _MPV_EVENT_PROPERTY_CHANGE:
                self._handle_property(event.data)

    def _handle_end_file(self, data: int | None) -> None:
        if not data:
            self._emit("error", self._current_session(), "libmpv ended without event details.")
            return
        detail = ctypes.cast(data, ctypes.POINTER(_MpvEventEndFile)).contents
        if detail.reason == _MPV_END_FILE_EOF:
            self._emit("eof", self._current_session())
        elif detail.reason == _MPV_END_FILE_ERROR:
            message = self._error_string(detail.error)
            self._emit("error", self._current_session(), message)
        else:
            self._emit("stopped", self._current_session())

    def _handle_property(self, data: int | None) -> None:
        if not data:
            return
        prop = ctypes.cast(data, ctypes.POINTER(_MpvEventProperty)).contents
        name = prop.name.decode("ascii", errors="replace") if prop.name else ""
        if not prop.data:
            return
        if prop.format == _MPV_FORMAT_DOUBLE:
            value: object = self._seconds_to_us(
                ctypes.cast(prop.data, ctypes.POINTER(ctypes.c_double)).contents.value
            )
        elif prop.format == _MPV_FORMAT_FLAG:
            value = bool(ctypes.cast(prop.data, ctypes.POINTER(ctypes.c_int)).contents.value)
        elif prop.format == _MPV_FORMAT_INT64:
            value = int(ctypes.cast(prop.data, ctypes.POINTER(ctypes.c_longlong)).contents.value)
        elif prop.format == _MPV_FORMAT_STRING:
            raw = ctypes.cast(prop.data, ctypes.POINTER(ctypes.c_char_p)).contents.value
            value = raw.decode("utf-8", errors="replace") if raw else ""
        else:
            return
        session_id = self._current_session()
        if name == "duration":
            self._emit("duration", session_id, value)
        elif name == "pause":
            self._emit("pause", session_id, value)
        elif name == "seekable":
            self._emit("seekable", session_id, value)
        elif name == "audio-codec-name":
            self._emit("codec", session_id, value)
        elif name == "audio-samplerate":
            self._emit("sample-rate", session_id, value)
        elif name == "audio-channels":
            self._emit("channels", session_id, value)

    def _set_property(self, name: str, value_format: int, value: Any) -> None:
        self._check(
            self._lib.mpv_set_property(
                self._ctx, name.encode("ascii"), value_format, ctypes.byref(value)
            ),
            f"set {name}",
        )

    def _command(self, *arguments: str, required: bool = True) -> None:
        encoded = [argument.encode("utf-8") for argument in arguments]
        args = (ctypes.c_char_p * (len(encoded) + 1))(*encoded, None)
        result = self._lib.mpv_command(self._ctx, args)
        if required:
            self._check(result, arguments[0] if arguments else "command")

    def _check(self, result: int, operation: str) -> None:
        if result < 0:
            raise PlayerBackendError(f"libmpv could not {operation}: {self._error_string(result)}")

    def _error_string(self, error: int) -> str:
        value = self._lib.mpv_error_string(error)
        return value.decode("utf-8", errors="replace") if value else f"error {error}"

    def _emit(self, name: str, session_id: int, value: object = None) -> None:
        with self._handler_lock:
            handler = self._handler
        if handler is not None:
            handler(BackendEvent(name=name, session_id=session_id, value=value))

    def _current_session(self) -> int:
        with self._session_lock:
            return self._active_session_id

    @staticmethod
    def _seconds_to_us(seconds: float) -> int:
        return int(seconds * 1_000_000 + 0.5)

    def _release_dll_directory(self) -> None:
        if self._dll_directory is not None:
            self._dll_directory.close()
            self._dll_directory = None
