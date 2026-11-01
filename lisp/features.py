"""The platform features ``(features)`` reports and ``cond-expand`` tests.

Only claims that are *true* belong here. The interpreter deliberately does not
report ``r7rs``: it is a documented subset, and a program that branches on
``r7rs`` should not be told it may rely on the whole report.
"""
from __future__ import annotations

import os
import platform
import sys

from .types import intern


def _architecture() -> str:
    """The machine name as a readable identifier, or nothing when unknown."""
    machine = platform.machine().lower()
    return {
        "x86_64": "x86-64",
        "amd64": "x86-64",
        "aarch64": "arm64",
        "arm64": "arm64",
        "i386": "x86",
        "i686": "x86",
    }.get(machine, "")


def feature_symbols(extra: list = ()) -> list:
    """The feature identifiers true of this host and this interpreter.

    *extra* is a profile's additional identifiers (``dsl-profile`` and the
    SRFI names under the DSL profile).
    """
    names = ["lisppy"]
    if os.name == "posix":
        names.append("posix")
    if sys.platform.startswith("darwin"):
        names.append("darwin")
    elif sys.platform.startswith("linux"):
        names.append("linux")
    elif os.name == "nt":
        names.append("windows")
    architecture = _architecture()
    if architecture:
        names.append(architecture)
    names.append("ieee-float")
    names.extend(extra)
    return [intern(name) for name in names]


def feature_names(extra: list = ()) -> frozenset[str]:
    return frozenset(str(symbol) for symbol in feature_symbols(extra))
