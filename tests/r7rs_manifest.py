"""The R7RS-small export manifest measured by ``tests/test_r7rs.py``.

The data itself lives in :mod:`shslisp.manifest`, where the library system
(:mod:`shslisp.library`) reads it to generate every built-in library's export
list — one source of truth, never typed twice. This module re-exports it so
the conformance harness keeps its documented import path.
"""

from shslisp.manifest import (  # noqa: F401  (re-exported for the harness)
    KNOWN_MISSING,
    MANIFEST,
    Library,
)

#: The dict's name in :mod:`shslisp.manifest`; ``LIBRARIES`` is what the harness
#: has always called it.
LIBRARIES = MANIFEST

__all__ = ["KNOWN_MISSING", "LIBRARIES", "Library"]
