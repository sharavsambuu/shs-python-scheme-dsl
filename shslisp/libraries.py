"""Which R7RS library names this interpreter can honestly provide.

The real library system lives next door in :mod:`shslisp.library`
(``define-library``/``import`` and the per-environment registry). This module
keeps the two small helpers everything shares: parsing a library-name value
into its parts, and recognising a plain feature identifier.
"""
from __future__ import annotations

from typing import Any

from .types import NIL, Symbol


def library_name(value: Any) -> tuple[str, ...]:
    """The parts of a library name value, e.g. ``("scheme", "base")``."""
    if value is NIL:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(part) for part in value)
    raise TypeError(f"expected a library name, got {type(value).__name__}")


def is_symbol_name(value: Any) -> bool:
    """True when *value* looks like a plain feature identifier."""
    return isinstance(value, Symbol)

