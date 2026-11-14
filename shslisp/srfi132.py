"""``(srfi 132)`` — sort libraries, core-backed on Python Timsort (S15).

Python's ``sorted`` is Timsort: stable, ``O(n log n)`` worst case, and written
in C — which is the whole argument for a core-backed library here. A
hand-written Scheme merge sort spends a trampoline step per comparison, and
the trading host's ``sort-agents-desc`` did exactly that on every bar. The
comparator is still the caller's Scheme procedure; only the call loop moved
across the seam.

``docs/SRFI_TASKS.md`` (S15) is the plan this implements. The library entry in
:mod:`shslisp.library` scopes the names; the primitives are core-*backed*
(installed into the library's own scope on first import), so the strict
``r7rs`` profile leaves them import-only.

**Scope** (the ledger's, audited name by name)::

    list-sorted? list-sort list-stable-sort
    vector-sorted? vector-sort vector-stable-sort

**Documented deviations** (``docs/srfi.md`` carries the list):

* The mutation half of SRFI 132 (``list-sort!``, ``list-stable-sort!``,
  ``vector-sort!``, ``vector-stable-sort!``) and the merge/median/selection
  procedures are **not** claimed. Nothing is shimmed; importing looks for the
  six exported names only.
* ``list-sort`` and ``list-stable-sort`` are the *same* implementation here
  and both are stable. SRFI 132 lets ``list-sort`` be unstable; being stable
  is a stronger guarantee, not a different answer.
* A comparator that is not a strict order is the caller's bug: Timsort is fed
  a three-way comparison derived from ``(< a b)`` / ``(< b a)``, and an
  inconsistent predicate yields *a* permutation, never a host crash.
"""

from __future__ import annotations

from functools import cmp_to_key
from typing import Any, Callable

from .env import Environment
from .errors import LispError, LispTypeError
from .evaluator import apply_procedure
from .types import (
    Primitive,
    Vector,
    intern,
    is_nil,
    is_procedure,
    is_true,
    list_to_python,
    make_list,
)

__all__ = ["install"]


# --------------------------------------------------------------------------- #
#  Argument gates                                                              #
# --------------------------------------------------------------------------- #

def _expect_ordering(value: Any, who: str) -> Any:
    if not is_procedure(value):
        raise LispTypeError(
            f"{who}: expected an ordering predicate, got {type(value).__name__}"
        )
    return value


def _expect_range(start: Any, end: Any, length: int, who: str) -> tuple[int, int]:
    """Validate an optional ``[start [end]]`` pair against *length*."""
    if start is False:
        return 0, length
    if isinstance(start, bool) or not isinstance(start, int):
        raise LispTypeError(f"{who}: expected an exact integer start, got {start!r}")
    if end is False:
        end = length
    if isinstance(end, bool) or not isinstance(end, int):
        raise LispTypeError(f"{who}: expected an exact integer end, got {end!r}")
    if not 0 <= start <= end <= length:
        raise LispTypeError(
            f"{who}: range [{start}, {end}) is not within 0..{length}"
        )
    return start, end


def _python_list(value: Any, who: str) -> list:
    if is_nil(value):
        return []
    try:
        return list_to_python(value)
    except LispError:
        raise LispTypeError(f"{who}: expected a list, got {value!r}") from None


def _python_vector(value: Any, who: str) -> list:
    if isinstance(value, Vector):
        return list(value.items)
    raise LispTypeError(f"{who}: expected a vector, got {value!r}")


def _three_way(ordering: Any) -> Callable[[Any, Any], int]:
    """A ``cmp`` for Timsort from the caller's ``(< a b)`` predicate."""

    def compare(a: Any, b: Any) -> int:
        if is_true(apply_procedure(ordering, [a, b])):
            return -1
        if is_true(apply_procedure(ordering, [b, a])):
            return 1
        return 0

    return compare


# --------------------------------------------------------------------------- #
#  The six operations                                                          #
# --------------------------------------------------------------------------- #

def _sorted(items: list, ordering: Any) -> list:
    if len(items) < 2:
        return items
    return sorted(items, key=cmp_to_key(_three_way(ordering)))


def _list_sorted(ordering: Any, lis: Any) -> bool:
    order = _expect_ordering(ordering, "list-sorted?")
    items = _python_list(lis, "list-sorted?")
    for left, right in zip(items, items[1:]):
        if is_true(apply_procedure(order, [right, left])):
            return False
    return True


def _list_sort(ordering: Any, lis: Any) -> Any:
    order = _expect_ordering(ordering, "list-sort")
    items = _python_list(lis, "list-sort")
    return make_list(_sorted(items, order))


def _vector_sorted(ordering: Any, vector: Any, start: Any = False, end: Any = False) -> bool:
    order = _expect_ordering(ordering, "vector-sorted?")
    items = _python_vector(vector, "vector-sorted?")
    low, high = _expect_range(start, end, len(items), "vector-sorted?")
    window = items[low:high]
    for left, right in zip(window, window[1:]):
        if is_true(apply_procedure(order, [right, left])):
            return False
    return True


def _vector_sort(ordering: Any, vector: Any, start: Any = False, end: Any = False) -> Vector:
    order = _expect_ordering(ordering, "vector-sort")
    items = _python_vector(vector, "vector-sort")
    low, high = _expect_range(start, end, len(items), "vector-sort")
    return Vector(_sorted(items[low:high], order))


# --------------------------------------------------------------------------- #
#  Installing                                                                  #
# --------------------------------------------------------------------------- #

def install(env: Environment) -> None:
    """Bind the ``(srfi 132)`` surface into *env* (the library's private scope)."""

    def define(name: str, fn: Any) -> None:
        env.define(intern(name), Primitive(name, fn))

    define("list-sorted?", _list_sorted)
    define("list-sort", _list_sort)
    # Stability is a property of the implementation here, so the two names
    # share one procedure; a caller reading either gets the documented answer.
    define("list-stable-sort", _list_sort)
    define("vector-sorted?", _vector_sorted)
    define("vector-sort", _vector_sort)
    define("vector-stable-sort", _vector_sort)
