"""``(srfi 125)`` — hash tables, core-backed (S14).

The storage is the core's :class:`shslisp.types.HashTable`: an
``equal?``-keyed Python ``dict`` whose keys are canonicalised by
:func:`shslisp.types.hash_key`, so a list or a vector can be a key without the
host ever insisting lists are unhashable. That makes every operation ``O(1)``
on average — the point of the library — where ``assoc``/``assq`` scans are
``O(N)``, which is what the trading host's correlation matrices and per-symbol
agent maps were spending trampoline steps on.

``docs/SRFI_TASKS.md`` (S14) is the plan this implements. The library entry in
:mod:`shslisp.library` scopes the names for the import/collision rules; the
primitives are core-*backed* (installed into the library's own scope on first
import), never core-bound, so the strict ``r7rs`` profile leaves them
import-only.

**Scope** (the ledger's, audited name by name)::

    make-hash-table hash-table? hash-table-ref hash-table-ref/default
    hash-table-set! hash-table-delete! hash-table-contains? hash-table-size
    hash-table-keys hash-table-values hash-table->alist alist->hash-table

Most of the names are the core primitives, re-exported as the same binding
objects; this module adds the three SRFI spellings the core does not have
(``hash-table-contains?``, ``hash-table-size``, ``alist->hash-table``).

**Documented deviations** (``docs/srfi.md`` carries the list):

* ``make-hash-table``'s optional comparator is accepted and ignored: the one
  storage is ``equal?``-keyed (SRFI 128 comparators are not scheduled here, so
  there is no second equivalence to honour). Passing one is not silently
  wrong — an ``equal?`` table is what the SRFI's default comparator requests.
* ``hash-table-ref`` answers a **thunk or a value** as its optional failure
  argument, the core's shape; with no failure argument a missing key raises a
  loud condition (never a silent ``#f``).
* ``hash-table->alist`` answers two-element lists ``(key value)``, and
  ``alist->hash-table`` accepts both those and dotted ``(key . value)`` pairs.
"""

from __future__ import annotations

from typing import Any

from .env import Environment
from .errors import LispTypeError
from .types import (
    HashTable,
    Pair,
    Primitive,
    intern,
    is_nil,
    is_pair,
    to_cells,
)

__all__ = ["install"]


# --------------------------------------------------------------------------- #
#  Argument gates                                                              #
# --------------------------------------------------------------------------- #

def _expect_table(value: Any, who: str) -> HashTable:
    if not isinstance(value, HashTable):
        raise LispTypeError(
            f"{who}: expected a hash table, got {type(value).__name__}"
        )
    return value


def _entries(alist: Any, who: str) -> list:
    """An association list as ``[(key, value), ...]``.

    Two entry shapes are accepted, both real alists in Scheme: the dotted
    ``(key . value)`` pair the SRFI writes, and the two-element list
    ``(key value)`` that :func:`shslisp.builtins`' ``hash-table->alist``
    produces. Anything else is a loud type error naming the offender.
    """
    if is_nil(alist):
        return []
    if not is_pair(alist):
        raise LispTypeError(f"{who}: expected an association list, got {alist!r}")
    try:
        items = to_cells(alist)
    except (LispTypeError, AttributeError):
        raise LispTypeError(f"{who}: expected an association list, got {alist!r}") from None
    out: list = []
    for item in items:
        if isinstance(item, Pair):
            out.append((item.car, item.cdr))
        elif isinstance(item, list) and len(item) == 2:
            out.append((item[0], item[1]))
        else:
            raise LispTypeError(
                f"{who}: every alist entry is a (key . value) pair or a "
                f"(key value) list, got {item!r}"
            )
    return out


# --------------------------------------------------------------------------- #
#  The SRFI-only procedures                                                    #
# --------------------------------------------------------------------------- #

def _hash_contains(table: Any, key: Any) -> bool:
    return _expect_table(table, "hash-table-contains?").has(key)


def _hash_size(table: Any) -> int:
    return len(_expect_table(table, "hash-table-size"))


def _alist_to_hash_table(alist: Any, *comparator: Any) -> HashTable:
    """``(alist->hash-table alist [comparator])`` — the comparator is ignored."""
    table = HashTable()
    for key, value in _entries(alist, "alist->hash-table"):
        table.set(key, value)
    return table


# --------------------------------------------------------------------------- #
#  Installing                                                                  #
# --------------------------------------------------------------------------- #

def install(env: Environment) -> None:
    """Bind the ``(srfi 125)`` surface into *env* (the library's private scope).

    The names the core already provides are inherited from the parent scope —
    one binding object, not a copy — so ``(eq? make-hash-table ...)`` holds
    through the import. Only the SRFI spellings are defined here.
    """

    def define(name: str, fn: Any) -> None:
        env.define(intern(name), Primitive(name, fn))

    define("hash-table-contains?", _hash_contains)
    define("hash-table-size", _hash_size)
    define("alist->hash-table", _alist_to_hash_table)
