"""Shared shape of metadata adapters used by the verified writer."""

from __future__ import annotations

from typing import Any, Protocol

from mtee.domain.metadata_edit import MetadataPatch


class MetadataAdapter(Protocol):
    """Format adapter that owns inspection, saving, and preservation checks."""

    def supports_path(self, path: Any) -> bool: ...

    def inspect(self, path: Any) -> tuple[Any, str]: ...

    def capabilities(
        self, path: Any, *, replace_aliases: bool = False
    ) -> dict[str, tuple[bool, str]]: ...

    def prepare(self, path: Any, patch: MetadataPatch) -> tuple[Any, Any]: ...

    def save(self, audio: Any, path: Any) -> None: ...

    def verify(self, path: Any, expected: Any, patch: MetadataPatch) -> None: ...
