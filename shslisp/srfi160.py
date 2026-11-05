"""``(srfi 160)`` — homogeneous numeric vectors, core-backed (S11).

The trading bridge: an ``f64vector`` is the type that speaks pandas/numpy.
The payload is a Python ``array.array`` (:class:`shslisp.types.Srfi160Vector`),
so the buffer protocol is the seam — ``numpy.frombuffer(vec.data)`` wraps an
``f64vector``'s doubles with zero copies, and a host can hand a numpy column's
bytes straight in. The operations are core-backed Python primitives (the
``(srfi 88)`` way), so a vectorized backing can serve them without the tree
walker. ``docs/SRFI_TASKS.md`` (S11) is the plan this implements.

**Scope** (the ledger's, and it is the audit's):

* ``(srfi 160 base)`` — the eight SRFI-4 procedures plus the ``@?`` validity
  predicate, for **all twelve** types;
* ``(srfi 160 f64)`` — the full SRFI-133-shaped operation set, plus
  ``make-f64vector-generator`` and ``write-f64vector``;
* the external representations ``#f64(...)``, ``#s8(...)``, ... — the reader
  and printer round-trip them (``#u8(`` stays the R7RS bytevector).

**Documented deviations** (``docs/srfi.md`` carries the list):

* ``@vector-comparator`` is **omitted** — it needs SRFI 128, which is not
  scheduled here. Nothing is shimmed.
* Valid elements are the spec's, enforced loudly: exact integers in range for
  the integer vectors, an *inexact* real (a Python ``float``) for ``f32``/
  ``f64``, an inexact complex for ``c64``/``c128``. An exact ``1`` is not an
  ``f64`` element — write ``1.0``.
* The other ten per-type full libraries do not exist yet; importing
  ``(srfi 160 u8)`` fails loudly. The kernel underneath is generic, so they
  are mechanical to add.
"""

from __future__ import annotations

from array import array
from fractions import Fraction
from typing import Any

from .env import Environment
from .errors import LispArityError, LispError, LispTypeError
from .evaluator import apply_procedure
from .types import (
    NIL,
    Primitive,
    Srfi160Vector,
    Symbol,
    Values,
    intern,
    is_true,
    make_list,
)

__all__ = ["install", "is_valid_element"]

#: The twelve types: name -> array typecode (complex types are interleaved).
_TYPE_CODES = {
    "u8": "B", "s8": "b", "u16": "H", "s16": "h",
    "u32": "I", "s32": "i", "u64": "Q", "s64": "q",
    "f32": "f", "f64": "d",
    "c64": "f", "c128": "d",
}
_COMPLEX_TYPES = ("c64", "c128")
_ALL_TYPES = tuple(_TYPE_CODES)

#: The exact-integer ranges, per SRFI 160's table.
_INT_RANGES = {
    "u8": (0, 255), "s8": (-128, 127),
    "u16": (0, 65535), "s16": (-32768, 32767),
    "u32": (0, 4_294_967_295), "s32": (-2_147_483_648, 2_147_483_647),
    "u64": (0, 18_446_744_073_709_551_615),
    "s64": (-9_223_372_036_854_775_808, 9_223_372_036_854_775_807),
}

#: The zero element each type defaults to.
_DEFAULTS = {"f32": 0.0, "f64": 0.0}


def is_valid_element(typecode: str, value: Any) -> bool:
    """The ``@?`` predicate: is *value* a valid element of a *typecode* vector?"""
    if typecode in _INT_RANGES:
        low, high = _INT_RANGES[typecode]
        return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
    if typecode in ("f32", "f64"):
        # An *inexact* real — a Python float. An exact 1 is not an f64 element.
        return isinstance(value, float)
    # c64/c128: an inexact complex number — a float is one too (R7RS makes
    # every real a complex).
    return isinstance(value, (float, complex))


def _expect_int(value: Any, who: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LispTypeError(f"{who}: expected an exact integer, got {value!r}")
    return value


def _expect_index(value: Any, who: str, length: int) -> int:
    index = _expect_int(value, who)
    if not 0 <= index < length:
        raise LispTypeError(f"{who}: index {index} out of range for {length} element(s)")
    return index


def _expect_vector(value: Any, who: str) -> Srfi160Vector:
    if not isinstance(value, Srfi160Vector):
        raise LispTypeError(f"{who}: expected a homogeneous vector, got {value!r}")
    return value


def _expect_typecode(value: Any, who: str) -> str:
    if isinstance(value, Symbol) and str(value) in _TYPE_CODES:
        return str(value)
    raise LispTypeError(f"{who}: {value!r} is not one of the twelve vector types")


# --------------------------------------------------------------------------- #
#  Element access                                                              #
# --------------------------------------------------------------------------- #

def _get(vec: Srfi160Vector, index: int) -> Any:
    if vec.typecode in _COMPLEX_TYPES:
        return complex(vec.data[2 * index], vec.data[2 * index + 1])
    return vec.data[index]


def _set(vec: Srfi160Vector, index: int, value: Any) -> None:
    if not is_valid_element(vec.typecode, value):
        raise LispTypeError(
            f"{vec.typecode}vector-set!: {value!r} is not a valid {vec.typecode} element"
        )
    try:
        if vec.typecode in _COMPLEX_TYPES:
            number = complex(value)
            vec.data[2 * index] = number.real
            vec.data[2 * index + 1] = number.imag
        else:
            vec.data[index] = value
    except OverflowError:
        raise LispTypeError(
            f"{vec.typecode}vector-set!: {value!r} does not fit the storage type"
        ) from None


def _new(typecode: str, length: int, fill: Any) -> Srfi160Vector:
    if typecode in _COMPLEX_TYPES:
        number = complex(fill)
        data = array(_TYPE_CODES[typecode], [number.real, number.imag] * length)
    else:
        data = array(_TYPE_CODES[typecode], [fill] * length)
    return Srfi160Vector(typecode, data)


def _default_fill(typecode: str) -> Any:
    if typecode in _COMPLEX_TYPES:
        return complex(0.0, 0.0)
    return _DEFAULTS.get(typecode, 0)


def _elements(vec: Srfi160Vector) -> list:
    return [_get(vec, i) for i in range(len(vec))]


def elements(vec: Srfi160Vector) -> list:
    """The vector's elements as Python numbers — the printer's view of it."""
    return _elements(vec)


def _check_typecode_of(vec: Srfi160Vector, typecode: str, who: str) -> Srfi160Vector:
    if vec.typecode != typecode:
        raise LispTypeError(f"{who}: expected a {typecode}vector, got a {vec.typecode}vector")
    return vec


def _range_args(args: Any, who: str, length: int) -> tuple:
    """``[start [end]]`` tail, clamped to 0..length like SRFI 133's."""
    if len(args) > 2:
        raise LispArityError(who, "at most 2 optional indices", len(args))
    start = _expect_int(args[0], who) if len(args) > 0 else 0
    end = _expect_int(args[1], who) if len(args) > 1 else length
    if not 0 <= start <= end <= length:
        raise LispTypeError(f"{who}: bad range {start}..{end} for {length} element(s)")
    return start, end


# --------------------------------------------------------------------------- #
#  The generic operation kernel (SRFI 133's shape, over a typecode)            #
# --------------------------------------------------------------------------- #

def _two_values(value: Any, who: str) -> tuple:
    if isinstance(value, Values):
        if len(value) != 2:
            raise LispError(f"{who}: the procedure must answer two values, got {len(value)}")
        return value[0], value[1]
    raise LispError(f"{who}: the procedure must answer two values (use (values ...))")


def _op_unfold(typecode: str, f: Any, length: Any, seed: Any, right: bool) -> Srfi160Vector:
    n = _expect_int(length, "@vector-unfold")
    if n < 0:
        raise LispTypeError(f"@vector-unfold: negative length {n}")
    vec = _new(typecode, n, _default_fill(typecode))
    state = seed
    indices = range(n - 1, -1, -1) if right else range(n)
    for i in indices:
        value, state = _two_values(apply_procedure(f, [i, state]), "@vector-unfold")
        _set(vec, i, value)
    return vec


def _op_copy(vec: Srfi160Vector, args: Any, who: str, reverse: bool = False) -> Srfi160Vector:
    start, end = _range_args(args, who, len(vec))
    result = _new(vec.typecode, end - start, _default_fill(vec.typecode))
    _op_copy_into(result, 0, vec, start, end, reverse=reverse)
    return result


def _op_copy_into(
    to: Srfi160Vector, at: int, from_vec: Srfi160Vector,
    start: int, end: int, reverse: bool = False,
) -> None:
    indices = range(end - 1, start - 1, -1) if reverse else range(start, end)
    for offset, i in enumerate(indices):
        if at + offset >= len(to):
            raise LispTypeError(
                f"{to.typecode}vector-copy!: the target has no room at index {at + offset}"
            )
        _set(to, at + offset, _get(from_vec, i))


def _op_append(vecs: Any, typecode: str, who: str) -> Srfi160Vector:
    checked = [_expect_vector(v, who) for v in vecs]
    total = sum(len(v) for v in checked)
    result = _new(typecode, total, _default_fill(typecode))
    at = 0
    for v in checked:
        _op_copy_into(result, at, v, 0, len(v))
        at += len(v)
    return result


def _op_append_subvectors(args: Any, typecode: str, who: str) -> Srfi160Vector:
    if len(args) % 3 != 0:
        raise LispArityError(who, "a multiple of 3 (vector start end)", len(args))
    spans = []
    total = 0
    for i in range(0, len(args), 3):
        vec = _expect_vector(args[i], who)
        start, end = _range_args(args[i + 1:i + 3], who, len(vec))
        spans.append((vec, start, end))
        total += end - start
    result = _new(typecode, total, _default_fill(typecode))
    at = 0
    for vec, start, end in spans:
        _op_copy_into(result, at, vec, start, end)
        at += end - start
    return result


def _numbers_equal(a: Any, b: Any) -> bool:
    # `=` on the elements — exactness matters exactly as the tower says.
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    return a == b


def _op_equal(vecs: Any) -> bool:
    checked = [_expect_vector(v, "@vector=") for v in vecs]
    if len(checked) < 2:
        raise LispArityError("@vector=", "at least 2", len(checked))
    first = checked[0]
    return all(
        len(v) == len(first)
        and all(_numbers_equal(_get(v, i), _get(first, i)) for i in range(len(v)))
        for v in checked[1:]
    )


def _op_take_drop(vec: Srfi160Vector, n: Any, who: str, take: bool, right: bool) -> Srfi160Vector:
    count = _expect_int(n, who)
    length = len(vec)
    if not 0 <= count <= length:
        raise LispTypeError(f"{who}: {count} is out of range for {length} element(s)")
    if take:
        window = range(length - count, length) if right else range(0, count)
    else:
        window = range(0, length - count) if right else range(count, length)
    result = _new(vec.typecode, len(window), _default_fill(vec.typecode))
    for offset, i in enumerate(window):
        _set(result, offset, _get(vec, i))
    return result


def _op_segment(vec: Srfi160Vector, n: Any) -> list:
    size = _expect_int(n, "@vector-segment")
    if size <= 0:
        raise LispError(f"@vector-segment: length must be a positive integer, got {size}")
    chunks = []
    i, length = 0, len(vec)
    while i < length:
        end = min(i + size, length)
        chunk = _new(vec.typecode, end - i, _default_fill(vec.typecode))
        _op_copy_into(chunk, 0, vec, i, end)
        chunks.append(chunk)
        i = end
    return chunks


def _op_fold(kons: Any, knil: Any, vecs: list, who: str, right: bool) -> Any:
    checked = [_expect_vector(v, who) for v in vecs]
    length = min(len(v) for v in checked)
    indices = range(length - 1, -1, -1) if right else range(length)
    acc = knil
    for i in indices:
        acc = apply_procedure(kons, [acc, *(_get(v, i) for v in checked)])
    return acc


def _op_map(f: Any, vecs: list, who: str, in_place: bool) -> Any:
    checked = [_expect_vector(v, who) for v in vecs]
    length = min(len(v) for v in checked)
    if in_place:
        target = checked[0]
        for v in checked:
            _check_typecode_of(v, target.typecode, who)
        for i in range(length):
            _set(target, i, apply_procedure(f, [_get(v, i) for v in checked]))
        return NIL
    result = _new(checked[0].typecode, length, _default_fill(checked[0].typecode))
    for i in range(length):
        _set(result, i, apply_procedure(f, [_get(v, i) for v in checked]))
    return result


def _op_count(pred: Any, vecs: list) -> int:
    length = min(len(v) for v in vecs)
    total = 0
    for i in range(length):
        if is_true(apply_procedure(pred, [_get(v, i) for v in vecs])):
            total += 1
    return total


def _op_for_each(f: Any, vecs: list, who: str) -> Any:
    """Iterate without collecting: the procedure's return value is ignored."""
    checked = [_expect_vector(v, who) for v in vecs]
    length = min(len(v) for v in checked)
    for i in range(length):
        apply_procedure(f, [_get(v, i) for v in checked])
    return NIL


def _op_cumulate(f: Any, knil: Any, vec: Srfi160Vector) -> Srfi160Vector:
    result = _new(vec.typecode, len(vec), _default_fill(vec.typecode))
    acc = knil
    for i in range(len(vec)):
        acc = apply_procedure(f, [acc, _get(vec, i)])
        _set(result, i, acc)
    return result


def _op_index(pred: Any, vecs: list, right: bool) -> Any:
    length = min(len(v) for v in vecs)
    indices = range(length - 1, -1, -1) if right else range(length)
    for i in indices:
        if is_true(apply_procedure(pred, [_get(v, i) for v in vecs])):
            return i
    return False


def _op_any(pred: Any, vecs: list) -> Any:
    length = min(len(v) for v in vecs)
    for i in range(length):
        result = apply_procedure(pred, [_get(v, i) for v in vecs])
        if is_true(result):
            return result
    return False


def _op_every(pred: Any, vecs: list) -> Any:
    length = min(len(v) for v in vecs)
    last: Any = True
    for i in range(length):
        result = apply_procedure(pred, [_get(v, i) for v in vecs])
        if not is_true(result):
            return False
        last = result
    return last


def _op_partition(pred: Any, vec: Srfi160Vector) -> Values:
    yes = _op_filter(pred, vec, keep=True)
    no = _op_filter(pred, vec, keep=False)
    result = _new(vec.typecode, len(vec), _default_fill(vec.typecode))
    _op_copy_into(result, 0, yes, 0, len(yes))
    _op_copy_into(result, len(yes), no, 0, len(no))
    return Values((result, len(yes)))


def _op_filter(pred: Any, vec: Srfi160Vector, keep: bool) -> Srfi160Vector:
    chosen = [
        _get(vec, i) for i in range(len(vec))
        if is_true(apply_procedure(pred, [_get(vec, i)])) == keep
    ]
    result = _new(vec.typecode, len(chosen), _default_fill(vec.typecode))
    for i, value in enumerate(chosen):
        _set(result, i, value)
    return result


def _op_fill(vec: Srfi160Vector, fill: Any, args: Any, who: str) -> Any:
    start, end = _range_args(args, who, len(vec))
    for i in range(start, end):
        _set(vec, i, fill)
    return NIL


def _op_reverse_in_place(vec: Srfi160Vector, args: Any, who: str) -> Any:
    start, end = _range_args(args, who, len(vec))
    i, j = start, end - 1
    while i < j:
        left, right = _get(vec, i), _get(vec, j)
        _set(vec, i, right)
        _set(vec, j, left)
        i, j = i + 1, j - 1
    return NIL


def _op_unfold_into(f: Any, vec: Srfi160Vector, start: Any, end: Any, seed: Any, right: bool) -> Any:
    s = _expect_int(start, "@vector-unfold!")
    e = _expect_int(end, "@vector-unfold!")
    if not 0 <= s <= e <= len(vec):
        raise LispTypeError(f"@vector-unfold!: bad range {s}..{e} for {len(vec)} element(s)")
    state = seed
    indices = range(e - 1, s - 1, -1) if right else range(s, e)
    for i in indices:
        value, state = _two_values(apply_procedure(f, [i, state]), "@vector-unfold!")
        _set(vec, i, value)
    return vec


def _op_swap(vec: Srfi160Vector, i: Any, j: Any) -> Any:
    a = _expect_index(i, "@vector-swap!", len(vec))
    b = _expect_index(j, "@vector-swap!", len(vec))
    left, right = _get(vec, a), _get(vec, b)
    _set(vec, a, right)
    _set(vec, b, left)
    return NIL


# --------------------------------------------------------------------------- #
#  Registration: (srfi 160 base) — the SRFI-4 eight plus @? for all 12 types   #
# --------------------------------------------------------------------------- #

def _make_prim(typecode: str) -> Any:
    name = f"make-{typecode}vector"

    def fn(*args: Any, _name: str = name, _tc: str = typecode) -> Srfi160Vector:
        if len(args) > 2:
            raise LispArityError(_name, "at most 2", len(args))
        n = _expect_int(args[0], _name)
        if n < 0:
            raise LispTypeError(f"{_name}: negative length {n}")
        fill = _default_fill(_tc) if len(args) < 2 else args[1]
        return _new(_tc, n, fill)

    return fn


def _ctor_prim(typecode: str) -> Any:
    def fn(*args: Any, _tc: str = typecode) -> Srfi160Vector:
        result = _new(_tc, len(args), _default_fill(_tc))
        for i, value in enumerate(args):
            _set(result, i, value)
        return result

    return fn


def install_base(env: Environment) -> None:
    """Bind ``(srfi 160 base)``: 8 procedures + the ``@?`` predicate, x12."""

    def define(name: str, fn: Any) -> None:
        env.define(intern(name), Primitive(name, fn))

    for tc in _ALL_TYPES:
        define(f"make-{tc}vector", _make_prim(tc))
        define(f"{tc}vector", _ctor_prim(tc))
        define(f"{tc}vector?", lambda v, _tc=tc: (
            isinstance(v, Srfi160Vector) and v.typecode == _tc))
        define(f"{tc}?", lambda v, _tc=tc: is_valid_element(_tc, v))

        def length_fn(v: Any, _tc: str = tc) -> int:
            return len(_checked_tc(v, _tc, f"{_tc}vector-length"))

        def ref_fn(v: Any, i: Any, _tc: str = tc) -> Any:
            vec = _checked_tc(v, _tc, f"{_tc}vector-ref")
            return _get(vec, _expect_index(i, f"{_tc}vector-ref", len(vec)))

        def set_fn(v: Any, i: Any, value: Any, _tc: str = tc) -> Any:
            vec = _checked_tc(v, _tc, f"{_tc}vector-set!")
            _set(vec, _expect_index(i, f"{_tc}vector-set!", len(vec)), value)
            return NIL

        def to_list_fn(v: Any, *args: Any, _tc: str = tc) -> list:
            vec = _checked_tc(v, _tc, f"{_tc}vector->list")
            start, end = _range_args(args, f"{_tc}vector->list", len(vec))
            return [_get(vec, i) for i in range(start, end)]

        def from_list_fn(lst: Any, _tc: str = tc) -> Srfi160Vector:
            if not isinstance(lst, list):
                raise LispTypeError(f"list->{_tc}vector: expected a list, got {lst!r}")
            result = _new(_tc, len(lst), _default_fill(_tc))
            for i, value in enumerate(lst):
                _set(result, i, value)
            return result

        define(f"{tc}vector-length", length_fn)
        define(f"{tc}vector-ref", ref_fn)
        define(f"{tc}vector-set!", set_fn)
        define(f"{tc}vector->list", to_list_fn)
        define(f"list->{tc}vector", from_list_fn)


def _checked_tc(v: Any, typecode: str, who: str) -> Srfi160Vector:
    return _check_typecode_of(_expect_vector(v, who), typecode, who)


# --------------------------------------------------------------------------- #
#  Registration: (srfi 160 f64) — the full SRFI-133-shaped set                 #
# --------------------------------------------------------------------------- #

_TC = "f64"


def _checked(v: Any, who: str) -> Srfi160Vector:
    return _checked_tc(v, _TC, who)


def _negated(pred: Any) -> Any:
    def fn(*args: Any) -> bool:
        return not is_true(apply_procedure(pred, list(args)))

    # A Primitive, not a bare function: apply_procedure only applies Lisp
    # procedure values.
    return Primitive("_negated-predicate", fn)


def _op_take_while(pred: Any, vec: Srfi160Vector, right: bool) -> Srfi160Vector:
    length = len(vec)
    if right:
        index = length
        while index > 0 and is_true(apply_procedure(pred, [_get(vec, index - 1)])):
            index -= 1
        window = range(index, length)
    else:
        index = 0
        while index < length and is_true(apply_procedure(pred, [_get(vec, index)])):
            index += 1
        window = range(0, index)
    result = _new(_TC, len(window), _default_fill(_TC))
    for offset, i in enumerate(window):
        _set(result, offset, _get(vec, i))
    return result


def _op_drop_while(pred: Any, vec: Srfi160Vector, right: bool) -> Srfi160Vector:
    length = len(vec)
    if right:
        index = length
        while index > 0 and is_true(apply_procedure(pred, [_get(vec, index - 1)])):
            index -= 1
        window = range(0, index)
    else:
        index = 0
        while index < length and is_true(apply_procedure(pred, [_get(vec, index)])):
            index += 1
        window = range(index, length)
    result = _new(_TC, len(window), _default_fill(_TC))
    for offset, i in enumerate(window):
        _set(result, offset, _get(vec, i))
    return result


def _copy_bang(to: Any, at: Any, frm: Any, *rest: Any, reverse: bool = False) -> Any:
    target = _checked(to, "f64vector-copy!")
    source = _checked(frm, "f64vector-copy!")
    position = _expect_int(at, "f64vector-copy!")
    start, end = _range_args(rest, "f64vector-copy!", len(source))
    _op_copy_into(target, position, source, start, end, reverse=reverse)
    return NIL


def _op_to_list(vec: Srfi160Vector, args: Any, who: str, reverse: bool = False) -> list:
    start, end = _range_args(args, who, len(vec))
    indices = range(end - 1, start - 1, -1) if reverse else range(start, end)
    return [_get(vec, i) for i in indices]


def _op_to_vector(vec: Srfi160Vector, args: Any, who: str) -> Any:
    from .types import Vector

    start, end = _range_args(args, who, len(vec))
    return Vector([_get(vec, i) for i in range(start, end)])


def _list_to(lst: Any) -> Srfi160Vector:
    return _from_python_list(lst, "list->f64vector", reverse=False)


def _reverse_list_to(lst: Any) -> Srfi160Vector:
    return _from_python_list(lst, "reverse-list->f64vector", reverse=True)


def _from_python_list(lst: Any, who: str, reverse: bool) -> Srfi160Vector:
    if not isinstance(lst, list):
        raise LispTypeError(f"{who}: expected a list, got {lst!r}")
    values = list(reversed(lst)) if reverse else lst
    result = _new(_TC, len(values), _default_fill(_TC))
    for i, value in enumerate(values):
        _set(result, i, value)
    return result


def _vector_to(vec: Any, *args: Any) -> Srfi160Vector:
    from .types import Vector

    if not isinstance(vec, Vector):
        raise LispTypeError(f"vector->f64vector: expected a vector, got {vec!r}")
    start, end = _range_args(args, "vector->f64vector", len(vec.items))
    result = _new(_TC, end - start, _default_fill(_TC))
    for offset, i in enumerate(range(start, end)):
        _set(result, offset, vec.items[i])
    return result


def _f64_generator(vec: Any, *args: Any) -> Any:
    source = _checked(vec, "make-f64vector-generator")
    start, end = _range_args(args, "make-f64vector-generator", len(source))
    state = {"i": start}

    def fn() -> Any:
        i = state["i"]
        if i >= end:
            from .types import EOF

            return EOF
        state["i"] = i + 1
        return _get(source, i)

    from .types import Primitive as _Primitive

    return _Primitive("f64vector-generator", fn)


def _write_f64vector(vec: Any, *rest: Any) -> Any:
    from .printer import to_string

    source = _checked(vec, "write-f64vector")
    text = to_string(source, write=True)
    if rest:
        port = rest[0]
        if not getattr(port, "writable", False):
            raise LispTypeError("write-f64vector: expected an output port")
        port.stream.write(text)
        return NIL
    return text


def install_f64(env: Environment) -> None:
    """Bind ``(srfi 160 f64)``: the SRFI-133-shaped operations, on f64."""

    def define(name: str, fn: Any) -> None:
        env.define(intern(name), Primitive(name, fn))

    def unary(who: str, handler: Any) -> Any:
        def fn(*args: Any) -> Any:
            vec = _checked(args[0], who)
            return handler(vec, args[1:], who)

        return fn

    # -- constructors -------------------------------------------------------- #
    define("make-f64vector", _make_prim(_TC))
    define("f64vector", _ctor_prim(_TC))
    define("f64vector-unfold", lambda f, n, seed: _op_unfold(_TC, f, n, seed, right=False))
    define("f64vector-unfold-right", lambda f, n, seed: _op_unfold(_TC, f, n, seed, right=True))
    define("f64vector-copy", unary("f64vector-copy", lambda v, rest, w: _op_copy(v, rest, w)))
    define("f64vector-reverse-copy", unary(
        "f64vector-reverse-copy", lambda v, rest, w: _op_copy(v, rest, w, reverse=True)))
    define("f64vector-append", lambda *vs: _op_append(vs, _TC, "f64vector-append"))
    define("f64vector-concatenate", lambda vs: _op_append(
        vs if isinstance(vs, list) else [], _TC, "f64vector-concatenate"))
    define("f64vector-append-subvectors", lambda *args: _op_append_subvectors(
        args, _TC, "f64vector-append-subvectors"))

    # -- predicates ---------------------------------------------------------- #
    define("f64?", lambda v: is_valid_element(_TC, v))
    define("f64vector?", lambda v: isinstance(v, Srfi160Vector) and v.typecode == _TC)
    define("f64vector-empty?", lambda v: len(_checked(v, "f64vector-empty?")) == 0)
    define("f64vector=", lambda *vs: _op_equal(vs))

    # -- selectors ----------------------------------------------------------- #
    define("f64vector-length", lambda v: len(_checked(v, "f64vector-length")))
    define("f64vector-ref", lambda v, i: _get(
        _checked(v, "f64vector-ref"), _expect_index(i, "f64vector-ref", len(v))))
    define("f64vector-set!", lambda v, i, x: (
        _set(_checked(v, "f64vector-set!"),
             _expect_index(i, "f64vector-set!", len(v)), x), NIL)[-1])

    # -- iteration ----------------------------------------------------------- #
    define("f64vector-take", lambda v, n: _op_take_drop(
        _checked(v, "f64vector-take"), n, "f64vector-take", take=True, right=False))
    define("f64vector-take-right", lambda v, n: _op_take_drop(
        _checked(v, "f64vector-take-right"), n, "f64vector-take-right", take=True, right=True))
    define("f64vector-drop", lambda v, n: _op_take_drop(
        _checked(v, "f64vector-drop"), n, "f64vector-drop", take=False, right=False))
    define("f64vector-drop-right", lambda v, n: _op_take_drop(
        _checked(v, "f64vector-drop-right"), n, "f64vector-drop-right", take=False, right=True))
    define("f64vector-segment", lambda v, n: _op_segment(_checked(v, "f64vector-segment"), n))
    define("f64vector-fold", lambda kons, knil, *vs: _op_fold(
        kons, knil, list(vs), "f64vector-fold", right=False))
    define("f64vector-fold-right", lambda kons, knil, *vs: _op_fold(
        kons, knil, list(vs), "f64vector-fold-right", right=True))
    define("f64vector-map", lambda f, *vs: _op_map(f, list(vs), "f64vector-map", in_place=False))
    define("f64vector-map!", lambda f, *vs: _op_map(f, list(vs), "f64vector-map!", in_place=True))
    define("f64vector-for-each", lambda f, *vs: _op_for_each(f, list(vs), "f64vector-for-each"))
    define("f64vector-count", lambda pred, *vs: _op_count(pred, list(vs)))
    define("f64vector-cumulate", lambda f, knil, v: _op_cumulate(
        f, knil, _checked(v, "f64vector-cumulate")))

    # -- searching ----------------------------------------------------------- #
    define("f64vector-take-while", lambda pred, v: _op_take_while(
        pred, _checked(v, "f64vector-take-while"), right=False))
    define("f64vector-take-while-right", lambda pred, v: _op_take_while(
        pred, _checked(v, "f64vector-take-while-right"), right=True))
    define("f64vector-drop-while", lambda pred, v: _op_drop_while(
        pred, _checked(v, "f64vector-drop-while"), right=False))
    define("f64vector-drop-while-right", lambda pred, v: _op_drop_while(
        pred, _checked(v, "f64vector-drop-while-right"), right=True))
    define("f64vector-index", lambda pred, *vs: _op_index(pred, list(vs), right=False))
    define("f64vector-index-right", lambda pred, *vs: _op_index(pred, list(vs), right=True))
    define("f64vector-skip", lambda pred, *vs: _op_index(_negated(pred), list(vs), right=False))
    define("f64vector-skip-right", lambda pred, *vs: _op_index(_negated(pred), list(vs), right=True))
    define("f64vector-any", lambda pred, *vs: _op_any(pred, list(vs)))
    define("f64vector-every", lambda pred, *vs: _op_every(pred, list(vs)))
    define("f64vector-partition", lambda pred, v: _op_partition(pred, _checked(v, "f64vector-partition")))
    define("f64vector-filter", lambda pred, v: _op_filter(pred, _checked(v, "f64vector-filter"), keep=True))
    define("f64vector-remove", lambda pred, v: _op_filter(pred, _checked(v, "f64vector-remove"), keep=False))

    # -- mutators ------------------------------------------------------------ #
    define("f64vector-swap!", lambda v, i, j: _op_swap(_checked(v, "f64vector-swap!"), i, j))
    define("f64vector-fill!", unary("f64vector-fill!", lambda v, rest, w: _op_fill(v, rest[0], rest[1:], w)))
    define("f64vector-reverse!", unary(
        "f64vector-reverse!", lambda v, rest, w: _op_reverse_in_place(v, rest, w)))
    define("f64vector-copy!", _copy_bang)
    define("f64vector-reverse-copy!", lambda to, at, frm, *rest: _copy_bang(
        to, at, frm, *rest, reverse=True))
    define("f64vector-unfold!", lambda f, v, start, end, seed: _op_unfold_into(
        f, _checked(v, "f64vector-unfold!"), start, end, seed, right=False))
    define("f64vector-unfold-right!", lambda f, v, start, end, seed: _op_unfold_into(
        f, _checked(v, "f64vector-unfold-right!"), start, end, seed, right=True))

    # -- conversion ---------------------------------------------------------- #
    define("f64vector->list", unary("f64vector->list", lambda v, rest, w: _op_to_list(v, rest, w)))
    define("reverse-f64vector->list", unary(
        "reverse-f64vector->list", lambda v, rest, w: _op_to_list(v, rest, w, reverse=True)))
    define("list->f64vector", _list_to)
    define("reverse-list->f64vector", _reverse_list_to)
    define("f64vector->vector", unary("f64vector->vector", lambda v, rest, w: _op_to_vector(v, rest, w)))
    define("vector->f64vector", _vector_to)

    # -- misc ---------------------------------------------------------------- #
    define("make-f64vector-generator", _f64_generator)
    define("write-f64vector", _write_f64vector)
    # `f64vector-comparator` is deliberately absent: it needs SRFI 128, which
    # is not scheduled. Documented in docs/srfi.md — nothing is shimmed.


def install(env: Environment) -> None:
    """Bind both SRFI 160 libraries' names into the core floor."""
    install_base(env)
    install_f64(env)
