"""``(srfi 180)`` — JSON, core-backed on Python's stdlib ``json`` (S17).

Standalone CLI scripts (the swarm capstone, the telemetry emitters) used to
concatenate JSON by hand — a quoting bug waiting to happen. This library is
the stdlib parser/printer behind two primitives, with the value mapping the
ledger pinned:

===============  ==========================================================
JSON             Scheme
===============  ==========================================================
object           association list of dotted ``("key" . value)`` pairs, keys
                 as **strings** (what ``assoc`` with a string finds)
array            vector (``#(...)``)
``null``         the symbol ``null``
``true``/``false``  the booleans ``#t`` / ``#f``
number           unchanged: an integer stays exact, a decimal stays inexact
string           string
===============  ==========================================================

``docs/SRFI_TASKS.md`` (S17) is the plan this implements. The library entry
in :mod:`shslisp.library` scopes the names; the primitives are core-*backed*
(installed into the library's own scope on first import), so the strict
``r7rs`` profile leaves them import-only.

**Scope**: ``json-read`` and ``json-write``, the two names the ledger claims.

**Documented deviations** (``docs/srfi.md`` carries the list):

* ``json-read`` takes the JSON **text** (a string), and ``json-write`` answers
  the JSON **text** (a string). SRFI 180's port-oriented spellings
  (``json-read-file``, the optional port argument, ``json-lines-*``) are not
  claimed; ``(write-string (json-write x) port)`` is the port path, with the
  ordinary port machinery.
* A JSON object with duplicate keys keeps the **last** value (the host dict's
  rule). The SRFI leaves duplicate keys unspecified.
* Encoding is deliberately one-way-honest: a symbol encodes as its JSON
  string (``buy`` → ``"buy"``), a dotted pair that is not an object entry is
  refused loudly, and ``'()`` encodes as ``[]`` — write ``'null`` for JSON
  ``null``. Malformed JSON and malformed values are loud :class:`LispError` /
  :class:`LispTypeError`, never a silent ``null``.
"""

from __future__ import annotations

import json as _json
from fractions import Fraction
from typing import Any

from .env import Environment
from .errors import LispError, LispTypeError
from .types import (
    Char,
    HashTable,
    Keyword,
    Pair,
    Primitive,
    Symbol,
    Vector,
    intern,
    is_nil,
    is_pair,
    make_list,
    to_cells,
)

__all__ = ["install"]

#: The symbol JSON ``null`` maps to (and from).
NULL = intern("null")


# --------------------------------------------------------------------------- #
#  Reading: JSON text -> Scheme values                                         #
# --------------------------------------------------------------------------- #

def _reject_constant(name: str) -> Any:
    # Python's json accepts NaN/Infinity by default; RFC 8259 does not, and a
    # silent NaN is exactly the telemetry bug this library exists to prevent.
    raise LispError(f"json-read: {name} is not valid JSON")


def _from_json(value: Any) -> Any:
    if value is None:
        return NULL
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return Vector(_from_json(item) for item in value)
    if isinstance(value, dict):
        return make_list([Pair(key, _from_json(item)) for key, item in value.items()])
    # `json.loads` only ever answers the shapes above.
    raise LispError(f"json-read: cannot represent {type(value).__name__}")  # pragma: no cover


def _json_read(text: Any) -> Any:
    if not isinstance(text, str) or isinstance(text, (Symbol, Keyword)):
        raise LispTypeError(f"json-read: expected JSON text, got {text!r}")
    try:
        parsed = _json.loads(text, parse_constant=_reject_constant)
    except ValueError as exc:
        raise LispError(f"json-read: {exc}") from None
    return _from_json(parsed)


# --------------------------------------------------------------------------- #
#  Writing: Scheme values -> JSON text                                         #
# --------------------------------------------------------------------------- #

def _key_text(candidate: Any) -> Any:
    """A JSON object key for *candidate*, or ``None`` when it is not a key."""
    if isinstance(candidate, Keyword):
        return str(candidate)
    if isinstance(candidate, Symbol):
        return str(candidate)
    if isinstance(candidate, str):
        return candidate
    return None


def _object_entry(entry: Any) -> Any:
    """The key text of an alist entry, or ``None`` when *entry* is not one."""
    if isinstance(entry, Pair):
        return _key_text(entry.car)
    if isinstance(entry, list) and len(entry) == 2:
        return _key_text(entry[0])
    return None


def _entry_value(entry: Any) -> Any:
    return entry.cdr if isinstance(entry, Pair) else entry[1]


def _is_object(items: list) -> bool:
    return bool(items) and all(_object_entry(entry) is not None for entry in items)


def _cells(value: Any, who: str) -> list:
    """A proper list or dotted pair chain as ``[car, ...]``."""
    try:
        return to_cells(value)
    except Exception:  # noqa: BLE001 - one answer for every malformed shape
        raise LispTypeError(f"{who}: expected a list, got {value!r}") from None


def _to_json(value: Any, who: str) -> Any:
    if value is NULL:
        return None
    if value is True or value is False:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Fraction):
        return float(value)
    if isinstance(value, str) and not isinstance(value, (Symbol, Keyword)):
        return value
    if isinstance(value, (Symbol, Keyword)):
        return str(value)
    if isinstance(value, Char):
        return value.value
    if isinstance(value, Vector):
        return [_to_json(item, who) for item in value.items]
    if isinstance(value, HashTable):
        out: dict = {}
        for key, item in value.entries():
            name = _key_text(key)
            if name is None:
                raise LispTypeError(
                    f"{who}: hash-table keys must be strings or symbols, got {key!r}"
                )
            out[name] = _to_json(item, who)
        return out
    if is_nil(value) or (isinstance(value, list) and not value):
        return []
    if isinstance(value, list) or is_pair(value):
        items = _cells(value, who)
        if _is_object(items):
            out = {}
            for entry in items:
                out[_object_entry(entry)] = _to_json(_entry_value(entry), who)
            return out
        for entry in items:
            if isinstance(entry, Pair):
                raise LispTypeError(
                    f"{who}: a dotted pair {entry!r} has no JSON representation"
                )
        return [_to_json(item, who) for item in items]
    raise LispTypeError(f"{who}: cannot encode {type(value).__name__} as JSON")


def _json_write(value: Any) -> str:
    return _json.dumps(_to_json(value, "json-write"), ensure_ascii=False)


# --------------------------------------------------------------------------- #
#  Installing                                                                  #
# --------------------------------------------------------------------------- #

def install(env: Environment) -> None:
    """Bind the ``(srfi 180)`` surface into *env* (the library's private scope)."""

    def define(name: str, fn: Any) -> None:
        env.define(intern(name), Primitive(name, fn))

    define("json-read", _json_read)
    define("json-write", _json_write)
