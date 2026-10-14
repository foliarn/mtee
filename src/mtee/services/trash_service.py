"""Recycle files through IFileOperation and retain the Shell recycle identity."""

from __future__ import annotations

import ctypes
import os
import uuid
from pathlib import Path

__all__ = ["TrashService", "TrashServiceError"]

_HRESULT = ctypes.c_long
_DWORD = ctypes.c_uint32
_S_OK = 0
_E_FAIL = -2147467259
_E_NOINTERFACE = -2147467262
_CLSCTX_INPROC_SERVER = 1
_COINIT_APARTMENTTHREADED = 0x2
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400
_SIGDN_DESKTOPABSOLUTEPARSING = 0x80028000
_IID_IUNKNOWN = uuid.UUID("00000000-0000-0000-C000-000000000046")
_IID_FILE_OPERATION = uuid.UUID("947AAB5F-0A5C-4C13-B4D6-4BF7836FC9F8")
_IID_PROGRESS_SINK = uuid.UUID("04B0F1A7-9490-44BC-96E1-4296A31252E2")
_CLSID_FILE_OPERATION = uuid.UUID("3AD05575-8857-4850-9277-11B85BDB8E09")


class _GUID(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_ubyte * 8),
    ]


def _guid(value: uuid.UUID) -> _GUID:
    return _GUID.from_buffer_copy(value.bytes_le)


def _com_call(
    instance: int | ctypes.c_void_p,
    index: int,
    result_type,
    argument_types: tuple,
    *arguments,
):
    vtable = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    method_type = ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)
    return method_type(vtable[index])(instance, *arguments)


class _RecycleReceiptSink:
    """Minimal COM progress sink that captures PostDeleteItem's new Shell item."""

    def __init__(self, shell32, ole32) -> None:
        self._shell32 = shell32
        self._ole32 = ole32
        self._references = 1
        self.recycle_item_identity = ""
        self.delete_error: int | None = None
        self.receipt_error: str | None = None
        callback = ctypes.WINFUNCTYPE

        def query_interface(this, iid_pointer, output_pointer):
            requested = uuid.UUID(bytes_le=ctypes.string_at(iid_pointer, 16))
            if requested not in {_IID_IUNKNOWN, _IID_PROGRESS_SINK}:
                ctypes.cast(output_pointer, ctypes.POINTER(ctypes.c_void_p))[0] = None
                return _E_NOINTERFACE
            ctypes.cast(output_pointer, ctypes.POINTER(ctypes.c_void_p))[0] = this
            self._references += 1
            return _S_OK

        def add_ref(_this):
            self._references += 1
            return self._references

        def release(_this):
            self._references = max(0, self._references - 1)
            return self._references

        def success(*_arguments):
            return _S_OK

        def post_delete(_this, _flags, _source_item, delete_result, recycled_item):
            if delete_result < 0:
                self.delete_error = int(delete_result)
                return _S_OK
            if not recycled_item:
                self.delete_error = _E_FAIL
                return _S_OK
            try:
                self.recycle_item_identity = _shell_item_name(
                    recycled_item, self._shell32, self._ole32
                )
                if not self.recycle_item_identity:
                    self.delete_error = _E_FAIL
                    self.receipt_error = "Windows returned an empty recycle-bin item identity."
            except Exception as error:
                self.delete_error = _E_FAIL
                self.receipt_error = f"Could not read the recycle-bin item identity: {error}"
            return _S_OK

        callback_specs = [
            ("QueryInterface", (ctypes.c_void_p, ctypes.c_void_p)),
            ("AddRef", ()),
            ("Release", ()),
            ("StartOperations", ()),
            ("FinishOperations", (_HRESULT,)),
            ("PreRenameItem", (_DWORD, ctypes.c_void_p, ctypes.c_wchar_p)),
            (
                "PostRenameItem",
                (_DWORD, ctypes.c_void_p, ctypes.c_wchar_p, _HRESULT, ctypes.c_void_p),
            ),
            (
                "PreMoveItem",
                (_DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p),
            ),
            (
                "PostMoveItem",
                (
                    _DWORD,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_wchar_p,
                    _HRESULT,
                    ctypes.c_void_p,
                ),
            ),
            (
                "PreCopyItem",
                (_DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_wchar_p),
            ),
            (
                "PostCopyItem",
                (
                    _DWORD,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_wchar_p,
                    _HRESULT,
                    ctypes.c_void_p,
                ),
            ),
            ("PreDeleteItem", (_DWORD, ctypes.c_void_p)),
            ("PostDeleteItem", (_DWORD, ctypes.c_void_p, _HRESULT, ctypes.c_void_p)),
            (
                "PreNewItem",
                (_DWORD, ctypes.c_void_p, ctypes.c_wchar_p, _DWORD, ctypes.c_wchar_p),
            ),
            (
                "PostNewItem",
                (
                    _DWORD,
                    ctypes.c_void_p,
                    ctypes.c_wchar_p,
                    _DWORD,
                    ctypes.c_wchar_p,
                    _HRESULT,
                    ctypes.c_void_p,
                ),
            ),
            ("UpdateProgress", (_DWORD, _DWORD)),
            ("ResetTimer", ()),
            ("PauseTimer", ()),
            ("ResumeTimer", ()),
        ]
        callback_functions = []
        for index, (name, argument_types) in enumerate(callback_specs):
            function = (
                query_interface
                if index == 0
                else add_ref
                if index == 1
                else release
                if index == 2
                else post_delete
                if name == "PostDeleteItem"
                else success
            )
            callback_functions.append(
                callback(ctypes.c_long, ctypes.c_void_p, *argument_types)(function)
            )
        vtable_type = type(
            "_RecycleReceiptVTable",
            (ctypes.Structure,),
            {
                "_fields_": [
                    (name, type(function))
                    for (name, _), function in zip(callback_specs, callback_functions, strict=True)
                ]
            },
        )
        self._callbacks = callback_functions
        self._vtable = vtable_type(*callback_functions)
        self._instance_type = type(
            "_RecycleReceiptInstance",
            (ctypes.Structure,),
            {
                "_fields_": [
                    ("vtable", ctypes.POINTER(vtable_type)),
                    ("references", ctypes.c_uint32),
                ]
            },
        )
        self._instance = self._instance_type(ctypes.pointer(self._vtable), self._references)
        self.pointer = ctypes.cast(ctypes.pointer(self._instance), ctypes.c_void_p)


def _shell_item_name(item: int | ctypes.c_void_p, shell32, ole32) -> str:
    name = ctypes.c_void_p()
    result = _com_call(
        item,
        5,
        _HRESULT,
        (_DWORD, ctypes.POINTER(ctypes.c_void_p)),
        _SIGDN_DESKTOPABSOLUTEPARSING,
        ctypes.byref(name),
    )
    if result < 0 or not name.value:
        raise OSError(result, "The Shell did not return a parsing identity for the recycled item.")
    try:
        return ctypes.wstring_at(name.value)
    finally:
        ole32.CoTaskMemFree(name)


class TrashServiceError(RuntimeError):
    """The Windows Shell did not confirm that a file entered the recycle bin."""


class TrashService:
    """Use IFileOperation on an STA worker and return its recycle-bin item identity."""

    def recycle(self, path: Path | str) -> str:
        if os.name != "nt":
            raise TrashServiceError("Windows recycle-bin support is unavailable on this system.")
        source = Path(path)
        if source.is_symlink() or not source.is_file():
            raise TrashServiceError("The selected audio file is no longer a regular file.")

        ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, _DWORD]
        ole32.CoInitializeEx.restype = _HRESULT
        ole32.CoUninitialize.argtypes = []
        ole32.CoUninitialize.restype = None
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole32.CoTaskMemFree.restype = None
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(_GUID),
            ctypes.c_void_p,
            _DWORD,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        ole32.CoCreateInstance.restype = _HRESULT
        shell32.SHCreateItemFromParsingName.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_void_p,
            ctypes.POINTER(_GUID),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        shell32.SHCreateItemFromParsingName.restype = _HRESULT

        initialized = False
        operation = ctypes.c_void_p()
        source_item = ctypes.c_void_p()
        cookie = _DWORD()
        sink = None
        result = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        if result < 0:
            raise OSError(result, "Could not initialize the Windows Shell apartment.")
        initialized = True
        try:
            clsid = _guid(_CLSID_FILE_OPERATION)
            iid = _guid(_IID_FILE_OPERATION)
            result = ole32.CoCreateInstance(
                ctypes.byref(clsid),
                None,
                _CLSCTX_INPROC_SERVER,
                ctypes.byref(iid),
                ctypes.byref(operation),
            )
            _check_hresult(result, "Could not create the Windows file operation.")

            shell_iid = _guid(uuid.UUID("43826D1E-E718-42EE-BC55-A1E261C37BFE"))
            result = shell32.SHCreateItemFromParsingName(
                str(source.resolve(strict=True)),
                None,
                ctypes.byref(shell_iid),
                ctypes.byref(source_item),
            )
            _check_hresult(result, "Could not open the selected file through the Windows Shell.")

            sink = _RecycleReceiptSink(shell32, ole32)
            flags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_NOERRORUI | _FOF_SILENT
            _check_hresult(
                _com_call(operation, 5, _HRESULT, (_DWORD,), flags),
                "Could not configure Windows Recycle Bin handling.",
            )
            _check_hresult(
                _com_call(
                    operation,
                    3,
                    _HRESULT,
                    (ctypes.c_void_p, ctypes.POINTER(_DWORD)),
                    sink.pointer,
                    ctypes.byref(cookie),
                ),
                "Could not observe the Windows recycle operation.",
            )
            _check_hresult(
                _com_call(
                    operation,
                    18,
                    _HRESULT,
                    (ctypes.c_void_p, ctypes.c_void_p),
                    source_item,
                    None,
                ),
                "Could not queue the Windows recycle operation.",
            )
            _check_hresult(
                _com_call(operation, 21, _HRESULT, ()),
                "Windows could not complete the recycle operation.",
            )
            aborted = ctypes.c_int()
            _check_hresult(
                _com_call(
                    operation,
                    22,
                    _HRESULT,
                    (ctypes.POINTER(ctypes.c_int),),
                    ctypes.byref(aborted),
                ),
                "Could not confirm the Windows recycle result.",
            )
            if aborted.value:
                raise TrashServiceError("The Windows Shell aborted the recycle operation.")
            if sink.delete_error is not None:
                _check_hresult(
                    sink.delete_error,
                    sink.receipt_error or "Windows did not confirm a Recycle Bin item.",
                )
            if not sink.recycle_item_identity:
                raise TrashServiceError("Windows did not return a Recycle Bin item identity.")
            return sink.recycle_item_identity
        finally:
            if operation.value and cookie.value:
                _com_call(operation, 4, _HRESULT, (_DWORD,), cookie)
            if source_item.value:
                _com_call(source_item, 2, _DWORD, ())
            if operation.value:
                _com_call(operation, 2, _DWORD, ())
            if initialized:
                ole32.CoUninitialize()


def _check_hresult(result: int, message: str) -> None:
    if result < 0:
        try:
            detail = ctypes.FormatError(result & 0xFFFFFFFF).strip()
        except (AttributeError, OSError):
            detail = f"HRESULT 0x{result & 0xFFFFFFFF:08X}"
        raise TrashServiceError(f"{message} {detail}")
