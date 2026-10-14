"""Characterization of TrashService: refusals, error mapping and the receipt sink.

The real Windows Shell is never invoked. ``ctypes.WinDLL`` and the COM call helper are replaced
by recorders, so the whole flow of ``recycle`` can be followed without touching any Recycle Bin.
Only files inside ``tmp_path`` are used.
"""

from __future__ import annotations

import ctypes
import os
import types
import uuid
from pathlib import Path
from typing import Any

import pytest

from mtee.services import trash_service
from mtee.services.trash_service import TrashService, TrashServiceError

windows_only = pytest.mark.skipif(
    os.name != "nt", reason="ctypes WinDLL/WINFUNCTYPE are Windows-only"
)

_E_FAIL = -2147467259
_ACCESS_DENIED = -2147024891  # 0x80070005
_FOF_ALLOWUNDO = 0x0040
# IFileOperation vtable slots used by the service.
_ADVISE, _UNADVISE, _SET_FLAGS, _DELETE_ITEM, _PERFORM, _ABORTED = 3, 4, 5, 18, 21, 22


class _Function:
    """A callable that accepts ``argtypes``/``restype`` like a ctypes foreign function."""

    argtypes: Any = None
    restype: Any = None

    def __init__(self, dll: _Dll, name: str) -> None:
        self._dll = dll
        self._name = name

    def __call__(self, *args: Any) -> int:
        return self._dll.invoke(self._name, *args)


class _Dll:
    """Minimal stand-in for ole32/shell32 that records calls and returns scripted HRESULTs."""

    def __init__(self) -> None:
        self.results: dict[str, int] = {}
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._functions: dict[str, _Function] = {}

    def __getattr__(self, name: str) -> _Function:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._functions.setdefault(name, _Function(self, name))

    def invoke(self, name: str, *args: Any) -> int:
        self.calls.append((name, args))
        result = self.results.get(name, 0)
        if name == "CoCreateInstance" and result >= 0:
            args[4]._obj.value = 0xA0  # the IFileOperation pointer
        if name == "SHCreateItemFromParsingName" and result >= 0:
            args[3]._obj.value = 0xB0  # the IShellItem pointer
        return result

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]


class _FakeSink:
    """Replaces the COM receipt sink; the test scripts what the Shell "reported"."""

    identity = ""
    delete_error: int | None = None
    receipt_error: str | None = None

    def __init__(self, _shell32: Any, _ole32: Any) -> None:
        self.recycle_item_identity = type(self).identity
        self.delete_error = type(self).delete_error
        self.receipt_error = type(self).receipt_error
        self.pointer = ctypes.c_void_p(0xC0)


class _Shell:
    """Installs the fakes into the module and records every COM vtable call."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.ole32 = _Dll()
        self.shell32 = _Dll()
        self.com_calls: list[tuple[int, int, tuple[Any, ...]]] = []
        self.com_results: dict[int, int] = {}
        self.aborted = 0
        self.libraries: list[str] = []

        def win_dll(name: str, use_last_error: bool = False) -> _Dll:
            self.libraries.append(name)
            return self.ole32 if name == "ole32" else self.shell32

        def com_call(instance: Any, index: int, _result_type: Any, _types: Any, *args: Any) -> int:
            value = getattr(instance, "value", instance)
            self.com_calls.append((int(value or 0), index, args))
            if index == _ADVISE:
                args[1]._obj.value = 7  # the advise cookie
            if index == _ABORTED:
                args[0]._obj.value = self.aborted
            return self.com_results.get(index, 0)

        monkeypatch.setattr(ctypes, "WinDLL", win_dll, raising=False)
        monkeypatch.setattr(trash_service, "_com_call", com_call)
        monkeypatch.setattr(trash_service, "_RecycleReceiptSink", _FakeSink)
        # The real FormatError cannot take a negative HRESULT, see the dedicated test below.
        monkeypatch.setattr(
            ctypes, "FormatError", lambda code: f"Windows detail {code:#x}.", raising=False
        )
        _FakeSink.identity = "C:\\$Recycle.Bin\\S-1\\$RABCDEF.wav"
        _FakeSink.delete_error = None
        _FakeSink.receipt_error = None

    def indexes(self) -> list[int]:
        return [index for _, index, _ in self.com_calls]


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "song.wav"
    path.write_bytes(b"RIFF....WAVE")
    return path


@pytest.fixture
def shell(monkeypatch: pytest.MonkeyPatch) -> _Shell:
    return _Shell(monkeypatch)


# --- refusals before the Shell ---------------------------------------------------------------


def test_recycle_refuses_to_run_outside_windows(
    monkeypatch: pytest.MonkeyPatch, audio: Path
) -> None:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the Shell must not be reached")

    monkeypatch.setattr(trash_service, "os", types.SimpleNamespace(name="posix"))
    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)

    with pytest.raises(TrashServiceError, match="Windows recycle-bin support is unavailable"):
        TrashService().recycle(audio)

    assert audio.is_file()


@windows_only
def test_recycle_refuses_a_missing_path_without_loading_the_shell(
    shell: _Shell, tmp_path: Path
) -> None:
    with pytest.raises(TrashServiceError, match="no longer a regular file"):
        TrashService().recycle(tmp_path / "absent.wav")
    assert shell.libraries == []


@windows_only
def test_recycle_refuses_a_directory_without_loading_the_shell(
    shell: _Shell, tmp_path: Path
) -> None:
    folder = tmp_path / "album"
    folder.mkdir()
    with pytest.raises(TrashServiceError, match="no longer a regular file"):
        TrashService().recycle(str(folder))
    assert shell.libraries == []
    assert folder.is_dir()


@windows_only
def test_recycle_refuses_a_symbolic_link(shell: _Shell, audio: Path, tmp_path: Path) -> None:
    link = tmp_path / "link.wav"
    try:
        link.symlink_to(audio)
    except OSError:
        pytest.skip("symbolic links need a privilege that is not available here")
    with pytest.raises(TrashServiceError, match="no longer a regular file"):
        TrashService().recycle(link)
    assert shell.libraries == []
    assert audio.is_file()
    assert link.is_symlink()


# --- flow with a scripted Shell --------------------------------------------------------------


@windows_only
def test_recycle_follows_the_ifileoperation_sequence_and_returns_the_identity(
    shell: _Shell, audio: Path
) -> None:
    identity = TrashService().recycle(audio)

    assert identity == "C:\\$Recycle.Bin\\S-1\\$RABCDEF.wav"
    assert shell.libraries == ["ole32", "shell32"]
    # flags, advise, queue delete, perform, aborted?, then unadvise and the two releases.
    assert shell.indexes() == [_SET_FLAGS, _ADVISE, _DELETE_ITEM, _PERFORM, _ABORTED, 4, 2, 2]
    assert shell.ole32.names() == [
        "CoInitializeEx",
        "CoCreateInstance",
        "CoUninitialize",
    ]
    # The path handed to the Shell is the resolved path of the file.
    assert shell.shell32.calls[0][1][0] == str(audio.resolve())
    assert audio.is_file()  # the fake Shell deleted nothing: the service itself never deletes


@windows_only
def test_recycle_always_asks_for_undo_so_the_file_goes_to_the_bin_not_to_oblivion(
    shell: _Shell, audio: Path
) -> None:
    TrashService().recycle(audio)
    flags = next(args[0] for _, index, args in shell.com_calls if index == _SET_FLAGS)
    assert flags & _FOF_ALLOWUNDO
    assert flags == 0x0040 | 0x0010 | 0x0400 | 0x0004
    # Only the queue-delete slot of IFileOperation is used; there is no permanent-delete call.
    assert shell.indexes().count(_DELETE_ITEM) == 1
    assert set(shell.indexes()) <= {
        _SET_FLAGS,
        _ADVISE,
        _UNADVISE,
        _DELETE_ITEM,
        _PERFORM,
        _ABORTED,
        2,
    }


@windows_only
def test_a_shell_abort_is_an_error_and_the_file_is_left_alone(shell: _Shell, audio: Path) -> None:
    shell.aborted = 1
    with pytest.raises(TrashServiceError, match="aborted the recycle operation"):
        TrashService().recycle(audio)
    assert audio.is_file()
    assert shell.ole32.names()[-1] == "CoUninitialize"


@windows_only
def test_a_delete_error_reported_by_the_sink_is_mapped_with_the_windows_detail(
    shell: _Shell, audio: Path
) -> None:
    _FakeSink.identity = ""
    _FakeSink.delete_error = _ACCESS_DENIED
    with pytest.raises(TrashServiceError) as caught:
        TrashService().recycle(audio)
    message = str(caught.value)
    assert message.startswith("Windows did not confirm a Recycle Bin item. ")
    assert len(message) > len("Windows did not confirm a Recycle Bin item. ")
    assert audio.is_file()


@windows_only
def test_a_receipt_error_message_replaces_the_generic_one(shell: _Shell, audio: Path) -> None:
    _FakeSink.identity = ""
    _FakeSink.delete_error = _E_FAIL
    _FakeSink.receipt_error = "Windows returned an empty recycle-bin item identity."
    with pytest.raises(TrashServiceError) as caught:
        TrashService().recycle(audio)
    assert str(caught.value).startswith("Windows returned an empty recycle-bin item identity. ")


@windows_only
def test_a_missing_identity_is_never_treated_as_a_success(shell: _Shell, audio: Path) -> None:
    _FakeSink.identity = ""
    with pytest.raises(
        TrashServiceError, match="Windows did not return a Recycle Bin item identity"
    ):
        TrashService().recycle(audio)
    assert audio.is_file()


@windows_only
@pytest.mark.parametrize(
    ("index", "message"),
    [
        (_SET_FLAGS, "Could not configure Windows Recycle Bin handling."),
        (_ADVISE, "Could not observe the Windows recycle operation."),
        (_DELETE_ITEM, "Could not queue the Windows recycle operation."),
        (_PERFORM, "Windows could not complete the recycle operation."),
        (_ABORTED, "Could not confirm the Windows recycle result."),
    ],
)
def test_a_failing_com_step_is_mapped_to_its_message_and_everything_is_released(
    shell: _Shell, audio: Path, index: int, message: str
) -> None:
    shell.com_results[index] = _E_FAIL
    with pytest.raises(TrashServiceError) as caught:
        TrashService().recycle(audio)
    assert str(caught.value).startswith(message + " ")
    assert shell.ole32.names()[-1] == "CoUninitialize"
    assert shell.indexes()[-2:] == [2, 2]  # source item and operation are released
    assert audio.is_file()


@windows_only
def test_a_failure_creating_the_file_operation_is_mapped_and_uninitializes_com(
    shell: _Shell, audio: Path
) -> None:
    shell.ole32.results["CoCreateInstance"] = _E_FAIL
    with pytest.raises(TrashServiceError) as caught:
        TrashService().recycle(audio)
    assert str(caught.value).startswith("Could not create the Windows file operation. ")
    assert shell.ole32.names() == ["CoInitializeEx", "CoCreateInstance", "CoUninitialize"]
    assert shell.com_calls == []


@windows_only
def test_a_failure_opening_the_file_in_the_shell_is_mapped(shell: _Shell, audio: Path) -> None:
    shell.shell32.results["SHCreateItemFromParsingName"] = _E_FAIL
    with pytest.raises(TrashServiceError) as caught:
        TrashService().recycle(audio)
    assert str(caught.value).startswith(
        "Could not open the selected file through the Windows Shell. "
    )
    assert shell.indexes() == [2]  # only the operation is released: there is no source item
    assert shell.ole32.names()[-1] == "CoUninitialize"
    assert audio.is_file()


@windows_only
def test_a_failing_apartment_initialisation_raises_an_oserror_not_a_service_error(
    shell: _Shell, audio: Path
) -> None:
    shell.ole32.results["CoInitializeEx"] = _E_FAIL
    with pytest.raises(OSError, match="Could not initialize the Windows Shell apartment") as caught:
        TrashService().recycle(audio)
    assert not isinstance(caught.value, TrashServiceError)
    assert shell.ole32.names() == ["CoInitializeEx"]  # nothing to uninitialize
    assert audio.is_file()


# --- pure helpers ----------------------------------------------------------------------------


def test_service_error_is_a_runtime_error() -> None:
    assert issubclass(TrashServiceError, RuntimeError)
    assert trash_service.__all__ == ["TrashService", "TrashServiceError"]


def test_guid_uses_the_little_endian_layout_of_com() -> None:
    value = uuid.UUID("947AAB5F-0A5C-4C13-B4D6-4BF7836FC9F8")
    guid = trash_service._guid(value)
    assert guid.data1 == 0x947AAB5F
    assert guid.data2 == 0x0A5C
    assert guid.data3 == 0x4C13
    assert bytes(guid.data4) == bytes.fromhex("B4D64BF7836FC9F8")
    assert bytes(guid) == value.bytes_le


def test_check_hresult_accepts_success_codes() -> None:
    trash_service._check_hresult(0, "ignored")
    trash_service._check_hresult(1, "ignored")


@windows_only
def test_check_hresult_prefixes_the_message_to_the_windows_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[int] = []

    def format_error(code: int) -> str:
        received.append(code)
        return " Access denied\r\n"

    monkeypatch.setattr(ctypes, "FormatError", format_error, raising=False)
    with pytest.raises(TrashServiceError) as caught:
        trash_service._check_hresult(_ACCESS_DENIED, "Could not do it.")
    assert str(caught.value) == "Could not do it. Access denied"
    # FormatError takes a signed C long, so the HRESULT is passed as is.
    assert received == [_ACCESS_DENIED]


@windows_only
@pytest.mark.parametrize("result", [_ACCESS_DENIED, _E_FAIL, -1])
def test_check_hresult_with_the_real_formaterror_reports_the_windows_text(result: int) -> None:
    # A negative HRESULT used to overflow FormatError; it now gives a TrashServiceError
    # carrying the (localized) Windows text after the message.
    with pytest.raises(TrashServiceError) as caught:
        trash_service._check_hresult(result, "Could not do it.")
    text = str(caught.value)
    assert text.startswith("Could not do it. ")
    assert len(text) > len("Could not do it. ")


def test_check_hresult_falls_back_to_the_hex_code_when_windows_has_no_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_text(_code: int) -> str:
        raise OSError("no message")

    monkeypatch.setattr(ctypes, "FormatError", no_text, raising=False)
    with pytest.raises(TrashServiceError) as caught:
        trash_service._check_hresult(_E_FAIL, "Failed.")
    assert str(caught.value) == "Failed. HRESULT 0x80004005"


@windows_only
def test_com_call_dispatches_through_the_vtable_slot() -> None:
    seen: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_uint32)

    def slot(this: int, value: int) -> int:
        seen.append(value)
        return 42

    callback = callback_type(slot)
    vtable = (ctypes.c_void_p * 4)()
    vtable[2] = ctypes.cast(callback, ctypes.c_void_p).value
    holder = ctypes.c_void_p(ctypes.addressof(vtable))
    result = trash_service._com_call(
        ctypes.addressof(holder), 2, ctypes.c_long, (ctypes.c_uint32,), 9
    )
    assert result == 42
    assert seen == [9]


@windows_only
def test_shell_item_name_reads_and_frees_the_parsing_name(monkeypatch: pytest.MonkeyPatch) -> None:
    buffer = ctypes.create_unicode_buffer("C:\\$Recycle.Bin\\$R1.wav")
    ole32 = _Dll()

    def com_call(_item: Any, index: int, _result: Any, _types: Any, *args: Any) -> int:
        assert index == 5
        assert args[0] == 0x80028000
        args[1]._obj.value = ctypes.addressof(buffer)
        return 0

    monkeypatch.setattr(trash_service, "_com_call", com_call)
    name = trash_service._shell_item_name(0xD0, object(), ole32)
    assert name == "C:\\$Recycle.Bin\\$R1.wav"
    assert ole32.names() == ["CoTaskMemFree"]


@windows_only
@pytest.mark.parametrize("result", [_E_FAIL, 0])
def test_shell_item_name_raises_when_the_shell_gives_no_name(
    monkeypatch: pytest.MonkeyPatch, result: int
) -> None:
    ole32 = _Dll()
    monkeypatch.setattr(trash_service, "_com_call", lambda *_a, **_k: result)
    with pytest.raises(OSError, match="did not return a parsing identity"):
        trash_service._shell_item_name(0xD0, object(), ole32)
    assert ole32.names() == []


# --- receipt sink (the COM callback object, driven from Python) ------------------------------

_POST_DELETE = 12
_QUERY_INTERFACE, _ADD_REF, _RELEASE = 0, 1, 2


@windows_only
class TestReceiptSink:
    def sink(self) -> trash_service._RecycleReceiptSink:
        return trash_service._RecycleReceiptSink(object(), _Dll())

    def post_delete(self, sink: Any, result: int, recycled: int | None) -> None:
        assert sink._callbacks[_POST_DELETE](None, 0, None, result, recycled) == 0

    def test_a_new_sink_has_no_receipt(self) -> None:
        sink = self.sink()
        assert sink.recycle_item_identity == ""
        assert sink.delete_error is None
        assert sink.receipt_error is None
        assert sink.pointer.value

    def test_a_failed_delete_records_the_hresult(self) -> None:
        sink = self.sink()
        self.post_delete(sink, _ACCESS_DENIED, 1)
        assert sink.delete_error == _ACCESS_DENIED
        assert sink.recycle_item_identity == ""

    def test_a_delete_without_a_recycled_item_is_an_error(self) -> None:
        sink = self.sink()
        self.post_delete(sink, 0, None)
        assert sink.delete_error == _E_FAIL
        assert sink.recycle_item_identity == ""

    def test_the_identity_of_the_recycled_item_is_captured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(trash_service, "_shell_item_name", lambda *_a: "C:\\$Recycle.Bin\\$R9")
        sink = self.sink()
        self.post_delete(sink, 0, 5)
        assert sink.recycle_item_identity == "C:\\$Recycle.Bin\\$R9"
        assert sink.delete_error is None

    def test_an_empty_identity_is_an_error_with_a_receipt_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(trash_service, "_shell_item_name", lambda *_a: "")
        sink = self.sink()
        self.post_delete(sink, 0, 5)
        assert sink.delete_error == _E_FAIL
        assert sink.receipt_error == "Windows returned an empty recycle-bin item identity."

    def test_an_exception_reading_the_identity_is_captured_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(*_args: Any) -> str:
            raise OSError("shell gone")

        monkeypatch.setattr(trash_service, "_shell_item_name", boom)
        sink = self.sink()
        self.post_delete(sink, 0, 5)
        assert sink.delete_error == _E_FAIL
        assert sink.receipt_error == "Could not read the recycle-bin item identity: shell gone"

    def test_query_interface_accepts_iunknown_and_the_progress_sink_only(self) -> None:
        sink = self.sink()
        query = sink._callbacks[_QUERY_INTERFACE]
        for accepted in (trash_service._IID_IUNKNOWN, trash_service._IID_PROGRESS_SINK):
            guid = trash_service._guid(accepted)
            out = ctypes.c_void_p()
            assert query(0x1234, ctypes.addressof(guid), ctypes.addressof(out)) == 0
            assert out.value == 0x1234
        unknown = trash_service._guid(trash_service._IID_FILE_OPERATION)
        out = ctypes.c_void_p(0x99)
        assert (
            query(0x1234, ctypes.addressof(unknown), ctypes.addressof(out))
            == trash_service._E_NOINTERFACE
        )
        assert out.value is None

    def test_reference_counting_never_goes_below_zero(self) -> None:
        sink = self.sink()
        assert sink._callbacks[_ADD_REF](None) == 2
        assert sink._callbacks[_RELEASE](None) == 1
        assert sink._callbacks[_RELEASE](None) == 0
        assert sink._callbacks[_RELEASE](None) == 0

    def test_the_other_progress_callbacks_succeed_silently(self) -> None:
        sink = self.sink()
        assert sink._callbacks[3](None) == 0  # StartOperations
        assert sink._callbacks[11](None, 0, None) == 0  # PreDeleteItem
        assert sink._callbacks[18](None) == 0  # ResumeTimer
        assert sink.delete_error is None
