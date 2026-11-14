"""``(srfi 152)`` — the string utilities the ledger scheduled (S18).

A reduced claim: seven names of the SRFI-152 surface, core-backed on Python
``str``. The full library (folds, unfolds, pads, segments, the searching
family) is not claimed — the ledger scoped what a trading CLI actually reaches
for: split a symbol list, join a path, find a needle, trim whitespace, test a
prefix or a suffix.

``docs/SRFI_TASKS.md`` (S18) is the plan this implements. The library entry in
:mod:`shslisp.library` scopes the names; the primitives are core-*backed*
(installed into the library's own scope on first import), so the strict
``r7rs`` profile leaves them import-only.

**Scope**::

    string-split string-join string-contains
    string-trim string-trim-both string-prefix? string-suffix?

**Documented deviation — ``string-trim`` trims BOTH ends.** SRFI 152 assigns
the left-only job to ``string-trim``, the right-only job to
``string-trim-right``, and both ends to ``string-trim-both``. This dialect's
core has always spelled the both-ends operation ``string-trim``
(``builtins.py``), and the locked S18 test pins that meaning:
``(string-trim "  hi  ")`` ⇒ ``"hi"``. Making the library's name left-only
would silently change an existing program the moment it imported the library,
so the core's meaning wins and ``string-trim-both`` is its alias. The
right-only spelling is not claimed. This is a real difference from a portable
SRFI 152 program and is listed again in ``docs/srfi.md``.

Other documented deviations:

* A trim predicate may be a character predicate (the SRFI's shape), a
  character, or a string of characters to strip — the three spellings a
  caller reaches for. The default is whitespace, as specified.
* ``string-split``'s optional ``limit`` refuses a negative integer; ``#f`` (or
  omission) means "as many splits as possible", as specified.
* ``string-split``, ``string-join`` and ``string-trim`` accept SRFI 152's
  optional arguments and therefore *supersede* the core's simpler
  two-argument spellings inside a scope that imports this library — which is
  what an explicit import means. ``string-contains`` (an index or ``#f``) is a
  different name from the core's ``string-contains?`` predicate, so the two
  coexist.
"""

from __future__ import annotations

from typing import Any, Callable

from .env import Environment
from .errors import LispError, LispTypeError
from .evaluator import apply_procedure
from .types import (
    NIL,
    Char,
    Keyword,
    Primitive,
    Symbol,
    intern,
    intern_char,
    is_nil,
    is_procedure,
    is_true,
    make_list,
    to_cells,
)

__all__ = ["install"]

#: "Argument not supplied" — distinct from ``#f``, so an explicit ``#f`` where
#: an index belongs is a type error rather than a silent default.
_UNSET = object()

_GRAMMARS = ("infix", "strict-infix", "suffix", "prefix")


# --------------------------------------------------------------------------- #
#  Argument gates                                                              #
# --------------------------------------------------------------------------- #

def _expect_string(value: Any, who: str) -> str:
    if isinstance(value, str) and not isinstance(value, (Symbol, Keyword)):
        return str(value)
    raise LispTypeError(f"{who}: expected a string, got {value!r}")


def _expect_index(value: Any, who: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LispTypeError(f"{who}: expected an exact integer, got {value!r}")
    return value


def _range(start: Any, end: Any, length: int, who: str) -> tuple[int, int]:
    low = 0 if start is _UNSET else _expect_index(start, who)
    high = length if end is _UNSET else _expect_index(end, who)
    if not 0 <= low <= high <= length:
        raise LispTypeError(f"{who}: range [{low}, {high}) is not within 0..{length}")
    return low, high


def _grammar(value: Any, who: str) -> str:
    if value is _UNSET:
        return "infix"
    name = str(value)
    if name not in _GRAMMARS:
        raise LispTypeError(
            f"{who}: grammar must be one of {', '.join(_GRAMMARS)}, got {value!r}"
        )
    return name


def _string_list(value: Any, who: str) -> list:
    if is_nil(value):
        return []
    try:
        items = to_cells(value)
    except Exception:  # noqa: BLE001 - one answer for every malformed shape
        raise LispTypeError(f"{who}: expected a list of strings, got {value!r}") from None
    return [_expect_string(item, who) for item in items]


def _char_test(spec: Any, who: str) -> Callable[[str], bool]:
    """A Python predicate over single characters from a Scheme trim argument."""
    if spec is _UNSET:
        return str.isspace
    if isinstance(spec, Char):
        target = spec.value
        return lambda ch: ch == target
    if isinstance(spec, str) and not isinstance(spec, (Symbol, Keyword)):
        allowed = str(spec)
        return lambda ch: ch in allowed
    if is_procedure(spec):
        return lambda ch: is_true(apply_procedure(spec, [intern_char(ch)]))
    raise LispTypeError(
        f"{who}: expected a character predicate, a character, or a "
        f"string of characters, got {spec!r}"
    )


# --------------------------------------------------------------------------- #
#  Trimming                                                                    #
# --------------------------------------------------------------------------- #

def _string_trim(
    string: Any, pred: Any = _UNSET, start: Any = _UNSET, end: Any = _UNSET
) -> str:
    text = _expect_string(string, "string-trim")
    low, high = _range(start, end, len(text), "string-trim")
    keep = _char_test(pred, "string-trim")
    begin, stop = low, high
    while begin < stop and keep(text[begin]):
        begin += 1
    while stop > begin and keep(text[stop - 1]):
        stop -= 1
    return text[begin:stop]


# --------------------------------------------------------------------------- #
#  Splitting and joining                                                       #
# --------------------------------------------------------------------------- #

def _string_split(
    string: Any,
    delimiter: Any,
    grammar: Any = _UNSET,
    limit: Any = _UNSET,
    start: Any = _UNSET,
    end: Any = _UNSET,
) -> Any:
    text = _expect_string(string, "string-split")
    separator = _expect_string(delimiter, "string-split")
    mode = _grammar(grammar, "string-split")
    low, high = _range(start, end, len(text), "string-split")
    segment = text[low:high]
    maximum: Any = _UNSET
    if limit is not _UNSET and limit is not False:
        maximum = _expect_index(limit, "string-split")
        if maximum < 0:
            raise LispTypeError(f"string-split: limit must be non-negative, got {maximum}")
    if segment == "":
        if mode == "strict-infix":
            raise LispError("string-split: an empty string has no words under 'strict-infix")
        return NIL
    if separator == "":
        parts = list(segment)
        if maximum is not _UNSET and 0 < maximum < len(parts):
            parts = [*parts[:maximum], "".join(parts[maximum:])]
    elif maximum is _UNSET:
        parts = segment.split(separator)
    else:
        parts = segment.split(separator, maximum)
    if mode == "prefix" and parts and parts[0] == "":
        parts = parts[1:]
    elif mode == "suffix" and parts and parts[-1] == "":
        parts = parts[:-1]
    return make_list(parts)


def _string_join(
    strings: Any, delimiter: Any = _UNSET, grammar: Any = _UNSET
) -> str:
    items = _string_list(strings, "string-join")
    between = " " if delimiter is _UNSET else _expect_string(delimiter, "string-join")
    mode = _grammar(grammar, "string-join")
    if not items:
        if mode == "strict-infix":
            raise LispError("string-join: an empty list has no words under 'strict-infix")
        return ""
    if mode == "suffix":
        return "".join(item + between for item in items)
    if mode == "prefix":
        return "".join(between + item for item in items)
    return between.join(items)


# --------------------------------------------------------------------------- #
#  Searching and affixes                                                       #
# --------------------------------------------------------------------------- #

def _string_contains(
    haystack: Any,
    needle: Any,
    start1: Any = _UNSET,
    end1: Any = _UNSET,
    start2: Any = _UNSET,
    end2: Any = _UNSET,
) -> Any:
    text = _expect_string(haystack, "string-contains")
    search = _expect_string(needle, "string-contains")
    low, high = _range(start1, end1, len(text), "string-contains")
    nlow, nhigh = _range(start2, end2, len(search), "string-contains")
    if nlow == nhigh:
        return low
    index = text.find(search[nlow:nhigh], low, high)
    return False if index < 0 else index


def _affix(
    who: str,
    front: bool,
    string1: Any,
    string2: Any,
    start1: Any = _UNSET,
    end1: Any = _UNSET,
    start2: Any = _UNSET,
    end2: Any = _UNSET,
) -> bool:
    first = _expect_string(string1, who)
    second = _expect_string(string2, who)
    low1, high1 = _range(start1, end1, len(first), who)
    low2, high2 = _range(start2, end2, len(second), who)
    piece = first[low1:high1]
    whole = second[low2:high2]
    return whole.startswith(piece) if front else whole.endswith(piece)


# --------------------------------------------------------------------------- #
#  Installing                                                                  #
# --------------------------------------------------------------------------- #

def install(env: Environment) -> None:
    """Bind the ``(srfi 152)`` subset into *env* (the library's private scope)."""

    def define(name: str, fn: Any) -> None:
        env.define(intern(name), Primitive(name, fn))

    define("string-split", _string_split)
    define("string-join", _string_join)
    define("string-contains", _string_contains)
    define("string-trim", _string_trim)
    define("string-trim-both", _string_trim)
    define("string-prefix?", lambda s1, s2, *rest: _affix("string-prefix?", True, s1, s2, *rest))
    define("string-suffix?", lambda s1, s2, *rest: _affix("string-suffix?", False, s1, s2, *rest))
