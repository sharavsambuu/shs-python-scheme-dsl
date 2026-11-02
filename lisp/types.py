"""The Lisp value universe.

There are only a handful of kinds of thing, and every one of them is an
ordinary Python value the host can inspect:

======================  =========================================
Lisp                    Python
======================  =========================================
number                  ``int`` / ``Fraction`` / ``Complex`` (exact),
                        ``float`` / ``complex`` (inexact) — one tower
boolean                 ``True`` / ``False`` (``#t`` / ``#f``)
string                  ``str``
symbol                  :class:`Symbol` (a ``str`` subclass)
character               :class:`Char` (``#\a``)
empty list / nil        :data:`NIL` (a singleton, and *true*)
proper list             a non-empty Python ``list``
improper pair           :class:`Pair` (``(cons 1 2)``)
vector                  :class:`Vector` (``#(1 2 3)``)
hash table              :class:`HashTable` (keys compared with ``equal?``)
tagged value            :class:`Tagged` (``(ok 3)`` — a *tag* plus fields)
closure                 :class:`Closure`
primitive               :class:`Primitive`
macro                   :class:`Macro`
opaque host value       anything else (a game, a Tx, a ``returns`` Result)
======================  =========================================

Three deliberate choices worth reading twice:

1. **Only ``#f`` is false.** R7RS semantics, not Python's: ``0``, ``""`` and
   the empty list are *true*. ``NIL`` keeps a false Python ``__bool__`` for the
   host's convenience, but Lisp decisions go through :func:`is_true`; a
   language where an empty score quietly means "false" is a language that
   lies.
2. **Symbols are interned.** ``(eq? 'a 'a)`` is ``#t`` by construction, so
   symbols are cheap to compare — which is what a Lisp reader spends its day
   doing.
3. **A proper list is a Python ``list``; only an *improper* pair is a
   :class:`Pair`.** That keeps the host bridge (which hands Python lists back
   and forth) unchanged, while still letting ``(cons 1 2)`` be a real pair:
   ``(cons 1 '(2))`` is the proper list ``[1, 2]``, and ``(cons 1 2)`` is the
   pair ``1 . 2``. ``car``/``cdr`` accept both.
4. **A tagged value is not a list, but it prints and destructures like one.**
   :class:`Tagged` carries a *tag* from a closed set — the thing ``match``
   dispatches on — and ``(ok 3)`` is ``Tagged("ok", [3])``. ``tagged?`` tells it
   from the list ``(ok 3)``; ``match`` deliberately accepts either, so a
   pattern written for a variant also reads a plain list of the same shape.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .env import Environment


# --------------------------------------------------------------------------- #
#  Symbols                                                                    #
# --------------------------------------------------------------------------- #

class Symbol(str):
    """An identifier. A ``str`` subclass, so it hashes and compares by name."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return str(self)


_SYMBOLS: dict[str, Symbol] = {}


def intern(name: str) -> Symbol:
    """Return the unique :class:`Symbol` for *name* (created on first sight)."""
    sym = _SYMBOLS.get(name)
    if sym is None:
        sym = Symbol(name)
        _SYMBOLS[name] = sym
    return sym


def is_symbol(value: Any) -> bool:
    return isinstance(value, Symbol)


# --------------------------------------------------------------------------- #
#  Keywords (SRFI 88)                                                         #
# --------------------------------------------------------------------------- #

class Keyword(str):
    """A keyword object: ``host:`` is one, ``:host`` is not.

    A keyword records its name *without* the trailing colon (which is what
    :func:`keyword_to_string` answers), but it prints with the colon so it
    reads back. It is self-evaluating and distinct from symbols: the value is
    a ``str`` subclass like :class:`Symbol`, but a sibling class — not a
    subclass — so ``symbol?`` and ``keyword?`` stay disjoint.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"{self}:"


_KEYWORDS: dict[str, Keyword] = {}


def intern_keyword(name: str) -> Keyword:
    """Return the unique :class:`Keyword` for *name* (no trailing colon)."""
    kw = _KEYWORDS.get(name)
    if kw is None:
        kw = Keyword(name)
        _KEYWORDS[name] = kw
    return kw


def is_keyword(value: Any) -> bool:
    return isinstance(value, Keyword)


# --------------------------------------------------------------------------- #
#  Nil and truthiness                                                          #
# --------------------------------------------------------------------------- #

class _Nil:
    """The empty list, spelled ``()`` — a singleton, and false."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "()"

    def __bool__(self) -> bool:
        return False


NIL = _Nil()


def is_nil(value: Any) -> bool:
    return value is NIL


def is_true(value: Any) -> bool:
    """R7RS truth: everything is true except ``#f``.

    The empty list is a *value*, not a boolean. ``NIL.__bool__`` stays false
    for host Python code, but Lisp control flow must ask this function, never
    ``bool``.
    """
    return value is not False


def make_list(items: Iterable[Any]) -> Any:
    """Build a proper list — ``NIL`` when there is nothing to hold."""
    out = list(items)
    return out if out else NIL


def list_to_python(value: Any) -> list:
    """A proper list (or ``NIL``) as a Python list; anything else raises.

    An improper pair is *not* a list, so it is refused here — which is exactly
    what makes ``(length (cons 1 2))`` an error rather than a quiet lie.
    """
    from .errors import LispTypeError

    if is_nil(value):
        return []
    if isinstance(value, list):
        return list(value)
    raise LispTypeError(f"expected a list, got {type(value).__name__}")


# --------------------------------------------------------------------------- #
#  Improper pairs                                                              #
# --------------------------------------------------------------------------- #

class Pair:
    """A cons cell whose tail is not a list: ``(cons 1 2)`` → ``1 . 2``.

    A proper list stays a Python ``list`` (see the module docstring); this
    class exists only so that the *last* cell of a chain can be something other
    than ``NIL``. A ``cdr`` that is another :class:`Pair` makes a dotted tail:
    ``(cons 1 (cons 2 3))`` is ``(1 2 . 3)``.
    """

    __slots__ = ("car", "cdr")

    def __init__(self, car: Any, cdr: Any) -> None:
        self.car = car
        self.cdr = cdr

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Pair):
            return NotImplemented
        return _structurally_equal(self.car, other.car) and _structurally_equal(
            self.cdr, other.cdr
        )

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"({self.car!r} . {self.cdr!r})"


def is_pair(value: Any) -> bool:
    """True for a cons cell: a non-empty proper list, or an improper :class:`Pair`."""
    return isinstance(value, Pair) or (isinstance(value, list) and bool(value))


def to_cells(value: Any) -> list:
    """Flatten a proper list or an improper pair chain into ``[car, ...]``.

    The final (non-pair) tail is dropped; use :func:`pair_tail` if you need it.
    """
    from .errors import LispTypeError

    if is_nil(value):
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, Pair):
        out: list = []
        node: Any = value
        while isinstance(node, Pair):
            out.append(node.car)
            node = node.cdr
        if not is_nil(node):
            raise LispTypeError("expected a proper list")
        return out
    raise LispTypeError(f"expected a list, got {type(value).__name__}")


def pair_tail(value: Any) -> Any:
    """The final cdr of a list/pair chain: ``NIL`` for a proper list."""
    if isinstance(value, Pair):
        node: Any = value
        while isinstance(node, Pair):
            node = node.cdr
        return node
    return NIL


def from_cells(cells: Iterable[Any], tail: Any = NIL) -> Any:
    """Build a proper list, or a dotted pair chain when *tail* is not ``NIL``."""
    items = list(cells)
    if is_nil(tail):
        return make_list(items)
    node = tail
    for item in reversed(items):
        node = Pair(item, node)
    return node


def _structurally_equal(a: Any, b: Any) -> bool:
    """``equal?`` for the Python-level ``==`` of :class:`Pair`/:class:`Vector`.

    The language's own ``equal`` lives in :mod:`lisp.evaluator`; importing it
    here would be a cycle, so it is fetched lazily. The two agree by design.
    """
    from .evaluator import equal

    return equal(a, b)


# --------------------------------------------------------------------------- #
#  Characters                                                                  #
# --------------------------------------------------------------------------- #

class Char:
    """A character (``#\\a``) — its own type, not a one-char string."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Char) and other.value == self.value

    def __hash__(self) -> int:
        return hash(("char", self.value))

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#\\{self.value}"


def is_char(value: Any) -> bool:
    return isinstance(value, Char)


_CHARS: dict[str, Char] = {}


def intern_char(value: str) -> Char:
    """The unique :class:`Char` for *value*, so ``(eq? #\\a #\\a)`` is ``#t``."""
    ch = _CHARS.get(value)
    if ch is None:
        ch = Char(value)
        _CHARS[value] = ch
    return ch


# --------------------------------------------------------------------------- #
#  Vectors                                                                     #
# --------------------------------------------------------------------------- #

class Vector:
    """A fixed-length, mutable sequence: ``#(1 2 3)``, ``(vector-ref v 0)``."""

    __slots__ = ("items",)

    def __init__(self, items: Iterable[Any] = ()) -> None:
        self.items: list = list(items)

    def __len__(self) -> int:
        return len(self.items)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Vector):
            return NotImplemented
        return len(self.items) == len(other.items) and all(
            _structurally_equal(a, b) for a, b in zip(self.items, other.items)
        )

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#({self.items!r})"


class MutableString:
    """A string that ``string-set!`` can mutate.

    Literals and most procedures keep returning Python ``str``; ``make-string``
    and ``string-copy`` return this wrapper because R7RS allows a freshly
    allocated string to be mutable. Every string primitive accepts it through
    :func:`lisp.builtins._expect_string`, which reads ``.text``; only the
    mutators insist on the wrapper, so a literal raises a clear "immutable"
    error instead of failing somewhere stranger.
    """

    __slots__ = ("chars",)

    def __init__(self, text: str = "") -> None:
        self.chars: list[str] = list(text)

    @property
    def text(self) -> str:
        return "".join(self.chars)

    def __str__(self) -> str:
        return self.text

    def __len__(self) -> int:
        return len(self.chars)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, MutableString):
            return self.chars == other.chars
        if isinstance(other, str):
            return self.text == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.text)

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#<mutable-string {self.text!r}>"


class ByteVector:
    """A fixed-length, mutable sequence of bytes: ``#u8(1 2 3)``.

    The payload is a Python ``bytearray`` so writes are cheap and the 0..255
    range is enforced at the boundary by the primitives. Do not add
    ``__eq__``: ``equal?`` handles bytevectors structurally, while ``eqv?``
    keeps R7RS's identity freedom for them.
    """

    __slots__ = ("data",)

    def __init__(self, data: Iterable[int] = ()) -> None:
        self.data: bytearray = bytearray(data)

    def __len__(self) -> int:
        return len(self.data)

    def __iter__(self):
        return iter(self.data)

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#u8({list(self.data)!r})"


# --------------------------------------------------------------------------- #
#  Tagged values — the carrier typed control flow dispatches on               #
# --------------------------------------------------------------------------- #

class Tagged:
    """A *tag* plus fields: the shape a closed variant constructs.

    ``(define-variant result (ok value) (err error))`` defines constructors, and
    ``(ok 3)`` returns ``Tagged('ok', [3])``. The tag comes from a declared,
    closed set, which is what makes ``match`` able to *name* the case it is
    missing instead of quietly choosing a default — the whole point of a typed
    control flow.

    A tagged value is **not** a list (``tagged?`` says so), but it prints as
    ``(ok 3)`` and *views* as the cells ``(tag . fields)``, so ``match`` can
    destructure it with an ordinary list pattern.
    """

    __slots__ = ("tag", "fields")

    def __init__(self, tag: Symbol, fields: Iterable[Any] = ()) -> None:
        self.tag: Symbol = tag
        self.fields: list = list(fields)

    def __len__(self) -> int:
        return 1 + len(self.fields)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Tagged):
            return NotImplemented
        return (
            self.tag == other.tag
            and len(self.fields) == len(other.fields)
            and all(_structurally_equal(a, b) for a, b in zip(self.fields, other.fields))
        )

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#<{self.tag} {' '.join(map(repr, self.fields))}>"


class RecordType:
    """The descriptor ``define-record-type`` binds its type name to.

    R7RS says the type name is bound to "a representation of the record type
    itself"; this is that representation. It is not a record and does not
    construct one — the constructor and predicate do that.
    """

    __slots__ = ("name", "field_names")

    def __init__(self, name: Symbol, field_names: Iterable[Symbol] = ()) -> None:
        self.name = name
        self.field_names = tuple(field_names)

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#<record-type {self.name}>"


class Record:
    """An R7RS record: a type name, ordered field values, and mutability.

    One generic class, not a Python class per record type — the Lisp program
    declares the shape at run time, so the value has to carry its own type
    name. Records compare by **identity** under ``eq?``/``eqv?``/``equal?``,
    as R7RS requires; do not give this class ``__eq__``.
    """

    __slots__ = ("type_name", "fields", "mutable")

    def __init__(
        self,
        type_name: Symbol,
        fields: Iterable[Any] = (),
        mutable: Iterable[bool] = (),
    ) -> None:
        self.type_name = type_name
        self.fields = list(fields)
        self.mutable = tuple(mutable)

    def __len__(self) -> int:
        return len(self.fields)

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#<record:{self.type_name} {' '.join(map(repr, self.fields))}>"


def is_tagged(value: Any) -> bool:
    return isinstance(value, Tagged)


def make_tagged(tag: Any, fields: Iterable[Any] = ()) -> Tagged:
    """Build a tagged value, refusing a non-symbol tag by name."""
    if not isinstance(tag, Symbol):
        from .errors import LispTypeError

        raise LispTypeError(f"a tag must be a symbol, got {to_repr(tag)}")
    return Tagged(tag, fields)


def tag_cells(value: Any) -> Optional[list]:
    """The *cells* of *value* — how ``match``'s list patterns read it.

    A :class:`Tagged` views as ``(tag . fields)``; a proper list is its items;
    ``NIL`` is the empty sequence. Anything that is not a sequence — an improper
    :class:`Pair`, a number, a string — returns ``None``, so no list pattern
    matches it. (An improper pair is deliberately not a sequence here: a list
    pattern has a definite arity, and ``(cons 1 2)`` does not.)
    """
    if isinstance(value, Tagged):
        return [value.tag, *value.fields]
    if isinstance(value, list):
        return list(value)
    if is_nil(value):
        return []
    return None


def to_repr(value: Any) -> str:
    """A short, dependency-free spelling of *value* for error messages.

    A local helper (rather than ``printer.to_string``) so :mod:`lisp.types` stays
    the bottom of the import graph: errors raised in the value layer must not
    drag the printer in.
    """
    if value is NIL:
        return "()"
    if value is True:
        return "#t"
    if value is False:
        return "#f"
    if isinstance(value, Symbol):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    return repr(value)


# --------------------------------------------------------------------------- #
#  The exact complex pair (C1)                                                 #
# --------------------------------------------------------------------------- #

def _exact_component(value: Any) -> Any:
    """A whole ``Fraction`` component is an ``int`` — one spelling per value."""
    if isinstance(value, Fraction) and value.denominator == 1:
        return int(value)
    return value


class Complex:
    """An exact complex number: two exact components, never a zero imaginary.

    R7RS 6.2.2 makes exactness a property of the *parts*, so the tower's
    complex half is a pair of exact numbers — Python's ``complex`` cannot
    represent ``1+2i`` exactly. The constructor normalizes the way the tower's
    other exact type does: a whole ``Fraction`` component collapses to
    ``int``, and an exact zero imaginary part collapses the whole value to
    its real part (an exact complex with no imaginary part *is* a real, so
    the constructor answers that real directly). Inexact complex values are
    plain ``complex``; any float in an operation contaminates the result.

    Only :mod:`lisp.builtins` builds these from program input (gated through
    ``_expect_number``/``_expect_real``); the class itself stays at the bottom
    of the import graph, dependency-free.
    """

    __slots__ = ("real", "imag")

    def __new__(cls, real: Any, imag: Any) -> Any:
        real = _exact_component(real)
        imag = _exact_component(imag)
        for part in (real, imag):
            if isinstance(part, (float, complex)):
                raise TypeError(
                    "Complex: an exact complex needs exact components; "
                    "use complex() for the inexact half"
                )
        if imag == 0:
            return real
        self = super().__new__(cls)
        self.real = real
        self.imag = imag
        return self

    def __init__(self, real: Any, imag: Any) -> None:
        # Normalization — and the zero-imaginary collapse, which may answer a
        # bare real instead of a Complex — happened in __new__.
        pass

    # -- arithmetic: exact/exact is schoolbook; a float contaminates -------- #

    def __add__(self, other: Any) -> Any:
        if isinstance(other, Complex):
            return Complex(self.real + other.real, self.imag + other.imag)
        if isinstance(other, (int, Fraction)):
            return Complex(self.real + other, self.imag)
        if isinstance(other, (float, complex)):
            return complex(self) + other
        return NotImplemented

    __radd__ = __add__  # addition commutes, and the parts are numbers

    def __sub__(self, other: Any) -> Any:
        if isinstance(other, Complex):
            return Complex(self.real - other.real, self.imag - other.imag)
        if isinstance(other, (int, Fraction)):
            return Complex(self.real - other, self.imag)
        if isinstance(other, (float, complex)):
            return complex(self) - other
        return NotImplemented

    def __rsub__(self, other: Any) -> Any:
        if isinstance(other, (int, Fraction)):
            return Complex(other - self.real, -self.imag)
        if isinstance(other, (float, complex)):
            return other - complex(self)
        return NotImplemented

    def __mul__(self, other: Any) -> Any:
        if isinstance(other, Complex):
            return Complex(
                self.real * other.real - self.imag * other.imag,
                self.real * other.imag + self.imag * other.real,
            )
        if isinstance(other, (int, Fraction)):
            return Complex(self.real * other, self.imag * other)
        if isinstance(other, (float, complex)):
            return complex(self) * other
        return NotImplemented

    __rmul__ = __mul__  # multiplication commutes over the complex field

    def __truediv__(self, other: Any) -> Any:
        if isinstance(other, Complex):
            # (a+bi)/(c+di) = ((ac+bd) + (bc−ad)i) / (c²+d²); the denominator
            # is zero only for the zero complex, which the constructor cannot
            # produce and the ``/`` primitive refuses before getting here.
            denom = other.real * other.real + other.imag * other.imag
            return Complex(
                Fraction(self.real * other.real + self.imag * other.imag, denom),
                Fraction(self.imag * other.real - self.real * other.imag, denom),
            )
        if isinstance(other, (int, Fraction)):
            if other == 0:
                raise ZeroDivisionError("division by zero")
            return Complex(Fraction(self.real, other), Fraction(self.imag, other))
        if isinstance(other, (float, complex)):
            return complex(self) / other
        return NotImplemented

    def __rtruediv__(self, other: Any) -> Any:
        if isinstance(other, (int, Fraction)):
            if other == 0:
                return 0  # 0/(a+bi) is exactly 0 — the collapse does the rest
            denom = self.real * self.real + self.imag * self.imag
            return Complex(
                Fraction(other * self.real, denom),
                Fraction(-other * self.imag, denom),
            )
        if isinstance(other, (float, complex)):
            return other / complex(self)
        return NotImplemented

    def __neg__(self) -> "Complex":
        return Complex(-self.real, -self.imag)

    def __pos__(self) -> "Complex":
        return self

    def __pow__(self, other: Any) -> Any:
        if isinstance(other, int) and not isinstance(other, bool):
            if other >= 0:
                result: Any = 1
                for _ in range(other):
                    result = result * self
                return result  # z⁰ is the exact real 1
            return 1 / self  # exact reciprocal; 0**negative is refused in _expt
        if isinstance(other, Fraction):
            # z ** (p/q) is generally irrational — the honest answer is inexact.
            return complex(self) ** float(other)
        if isinstance(other, (float, complex)):
            return complex(self) ** other
        return NotImplemented

    def __rpow__(self, other: Any) -> Any:
        if isinstance(other, (int, Fraction, float)):
            return complex(other) ** complex(self)
        if isinstance(other, complex):
            return other ** complex(self)
        return NotImplemented

    def __abs__(self) -> Any:
        """|a+bi| = √(a²+b²): exact when the sum of squares is a perfect
        rational square — |3+4i| is 5 — and honestly inexact otherwise."""
        total = Fraction(self.real) ** 2 + Fraction(self.imag) ** 2
        root_n = math.isqrt(total.numerator)
        root_d = math.isqrt(total.denominator)
        if root_n * root_n == total.numerator and root_d * root_d == total.denominator:
            return _exact_component(Fraction(root_n, root_d))
        return math.hypot(float(self.real), float(self.imag))

    def __complex__(self) -> complex:
        """The inexact image — the contagion target and the hash basis."""
        return complex(float(self.real), float(self.imag))

    # -- equality: exact components, exact comparison ----------------------- #

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Complex):
            return self.real == other.real and self.imag == other.imag
        if isinstance(other, (int, Fraction)):
            return self.imag == 0 and self.real == other  # imag is never 0
        if isinstance(other, float):
            return False  # a nonzero imaginary part is not a real
        if isinstance(other, complex):
            # Component-wise, and exact: Python's int/Fraction == float does
            # not round through the double, so (= 1+2i 1.0+2.0i) is honest.
            return self.real == other.real and self.imag == other.imag
        return NotImplemented

    def __hash__(self) -> int:
        try:
            # Python's own complex hash, on the double images: values that
            # compare equal hash equal across the exactness boundary — the
            # same promise hash(1) == hash(1.0) makes.
            return hash(complex(self))
        except OverflowError:
            # No double can equal a component this large, so the boundary
            # promise does not constrain the spelling.
            return hash((self.real, self.imag))

    def __repr__(self) -> str:
        return f"Complex({self.real!r}, {self.imag!r})"


# --------------------------------------------------------------------------- #
#  Hash tables                                                                 #
# --------------------------------------------------------------------------- #

def hash_key(value: Any) -> Any:
    """A hashable token for *value* under ``equal?`` semantics.

    ``equal?`` compares lists and vectors structurally but host objects by
    identity, so the token does the same — that is what lets a hash table be
    keyed by a list without Python insisting lists are unhashable.
    """
    if value is True or value is False:
        return ("bool", value)
    if value is NIL:
        return ("nil",)
    if isinstance(value, (int, float, Fraction, Complex, complex)):
        return ("num", value)
    if isinstance(value, Symbol):
        return ("sym", str(value))
    if isinstance(value, Keyword):
        return ("keyword", str(value))
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, MutableString):
        return ("str", value.text)
    if isinstance(value, Char):
        return ("char", value.value)
    if isinstance(value, list):
        return ("list", tuple(hash_key(x) for x in value))
    if isinstance(value, Pair):
        return ("pair", hash_key(value.car), hash_key(value.cdr))
    if isinstance(value, Vector):
        return ("vec", tuple(hash_key(x) for x in value.items))
    if isinstance(value, ByteVector):
        return ("u8", bytes(value.data))
    if isinstance(value, Tagged):
        return ("tag", str(value.tag), tuple(hash_key(x) for x in value.fields))
    if isinstance(value, HashTable):
        return ("hash", id(value))
    return ("obj", id(value))


class HashTable:
    """An ``equal?``-keyed dictionary; iteration follows insertion order."""

    __slots__ = ("_entries",)

    def __init__(self, entries: Optional[Iterable[Any]] = None) -> None:
        self._entries: dict = {}
        if entries is not None:
            for key, value in entries:
                self.set(key, value)

    def set(self, key: Any, value: Any) -> None:
        self._entries[hash_key(key)] = (key, value)

    def get(self, key: Any, default: Any = False) -> Any:
        entry = self._entries.get(hash_key(key))
        return entry[1] if entry is not None else default

    def has(self, key: Any) -> bool:
        return hash_key(key) in self._entries

    def delete(self, key: Any) -> bool:
        return self._entries.pop(hash_key(key), None) is not None

    def entries(self) -> list:
        return list(self._entries.values())

    def keys(self) -> list:
        return [key for key, _ in self._entries.values()]

    def values(self) -> list:
        return [value for _, value in self._entries.values()]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#<hash-table {len(self._entries)}>"


# --------------------------------------------------------------------------- #
#  Error objects                                                               #
# --------------------------------------------------------------------------- #

class ErrorObject:
    """The condition ``error`` raises: a message plus its irritants.

    A dedicated type (rather than a bare string) is what lets ``guard`` tell a
    structured error from an arbitrary value a program ``raise``d.
    """

    __slots__ = ("message", "irritants", "kind")

    def __init__(
        self,
        message: str,
        irritants: Optional[Iterable[Any]] = None,
        kind: Optional[str] = None,
    ) -> None:
        self.message = message
        self.irritants: list = list(irritants) if irritants is not None else []
        #: ``"file"`` or ``"read"`` when the condition came from that family.
        self.kind = kind

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return f"#<error {self.message!r}>"


def is_error_object(value: Any) -> bool:
    return isinstance(value, ErrorObject)


class EOFObject:
    """The unique end-of-file object: ``(eof-object)`` / ``(eof-object? x)``.

    A singleton, like ``NIL``, so ``(eof-object? x)`` is an identity test and a
    program can compare against the value it was handed without importing a
    constructor. It is deliberately *not* false: reaching the end of a stream is
    data, not failure.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        return "#<eof>"


#: The one end-of-file value. Compare with ``is``.
EOF = EOFObject()


# --------------------------------------------------------------------------- #
#  Ports — the language's first-class I/O handles                              #
# --------------------------------------------------------------------------- #

class Port:
    """A handle on a text stream: a file, a string, or the program's stdio.

    Two booleans say which ways it may be used — a Scheme port can be input,
    output, or both — and ``closed`` is the one piece of mutable state, so a
    program can ask ``(port? p)`` of a closed port without an exception. The
    wrapped ``stream`` is an ordinary Python text file object, which is the
    whole point: the host's I/O *is* the language's I/O, with a name on it.
    """

    __slots__ = ("stream", "readable", "writable", "name", "closed", "binary", "buffer")

    def __init__(
        self,
        stream: Any,
        *,
        readable: bool = False,
        writable: bool = False,
        name: str = "<port>",
        binary: bool = False,
    ) -> None:
        self.stream = stream
        self.readable = readable
        self.writable = writable
        self.name = name
        self.closed = False
        #: A binary port wraps a bytes stream; a textual one wraps text.
        self.binary = binary
        #: Text already read from a non-seekable stream but not yet consumed.
        self.buffer = ""

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self.stream.close()
            except (OSError, ValueError):  # pragma: no cover - host-dependent
                pass

    def __repr__(self) -> str:  # pragma: no cover - the printer is used instead
        kind = "input" if self.readable and not self.writable else (
            "output" if self.writable and not self.readable else "input/output"
        )
        return f"#<{kind}-port {self.name}>"


# --------------------------------------------------------------------------- #
#  Multiple values                                                             #
# --------------------------------------------------------------------------- #

class Values(tuple):
    """The bundle ``(values a b)`` builds, unpacked by ``call-with-values``.

    It is a ``tuple`` so a host can read it directly; in any single-value
    context it is simply an opaque value.
    """

    __slots__ = ()


# --------------------------------------------------------------------------- #
#  Procedures                                                                  #
# --------------------------------------------------------------------------- #

#: A callable a macro/lambda parameter list can take: an ordinary parameter
#: plus an optional rest parameter after a ``.`` (``(a b . rest)``).
@dataclass
class Closure:
    """A user-defined procedure: parameters, body, and the captured scope."""

    params: list[Symbol]
    rest: Optional[Symbol]
    body: list
    env: "Environment"
    name: str = "lambda"

    def arity(self) -> str:
        fixed = len(self.params)
        if self.rest is not None:
            return f"at least {fixed}"
        return str(fixed)


@dataclass
class Macro:
    """A procedure that rewrites code before it is evaluated.

    Parameters and body look exactly like a :class:`Closure`; the difference
    is *when* it runs. A closure receives evaluated arguments; a macro receives
    the raw forms, and whatever it returns is evaluated in the caller's place.
    That is the whole trick behind ``while`` and ``++`` in the prelude.

    ``defmacro`` is deliberately *unhygienic*: it is the raw tool, and a macro
    whose template binds a name the caller also uses can capture it (use
    ``gensym``). For macros that are hygienic by construction, use
    ``define-syntax`` with ``syntax-rules`` (:class:`SyntaxRules`).
    """

    params: list[Symbol]
    rest: Optional[Symbol]
    body: list
    env: "Environment"
    name: str = "macro"


@dataclass
class SyntaxRules:
    """A hygienic macro: ``(define-syntax name (syntax-rules (lit...) (pat tmpl)...))``.

    Expansion matches the use against each ``(pattern template)`` clause and
    instantiates the first that fits, renaming identifiers the template
    introduces so they cannot capture — or be captured by — the caller's names.

    ``aliases`` pins each free template identifier to the binding it had where
    the macro was defined; ``cache`` memoises an expansion per rendered use, so
    a macro called in a loop does not re-expand (or leak fresh names) each time.
    """

    name: str
    literals: frozenset
    rules: list
    env: "Environment"
    aliases: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)


class Primitive:
    """A procedure implemented in Python. ``fn`` is called with raw args."""

    __slots__ = ("name", "fn")

    def __init__(self, name: str, fn: Callable[..., Any]) -> None:
        self.name = name
        self.fn = fn

    def __repr__(self) -> str:  # pragma: no cover
        return f"#<primitive {self.name}>"


def is_procedure(value: Any) -> bool:
    return isinstance(value, (Closure, Primitive))
