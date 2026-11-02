"""Writing Lisp values back out.

``to_string`` is the single formatter. ``write`` mode quotes strings (so a
value can be read back), ``display`` mode does not (so a human can read it) —
the same split Scheme draws, and the reason ``(display "hi")`` prints ``hi``
but ``(write "hi")`` prints ``"hi"``.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any

from .types import (
    NIL,
    ByteVector,
    Char,
    Closure,
    EOF,
    ErrorObject,
    HashTable,
    Keyword,
    Macro,
    MutableString,
    Pair,
    Primitive,
    Port,
    Record,
    RecordType,
    Symbol,
    SyntaxRules,
    Tagged,
    Values,
    Vector,
    is_nil,
)


def to_string(value: Any, write: bool = False) -> str:
    """Render *value* as text. ``write=True`` makes it reader-friendly."""
    if value is NIL:
        return "()"
    if value is True:
        return "#t"
    if value is False:
        return "#f"
    if isinstance(value, Symbol):
        return _symbol_text(value)
    if isinstance(value, Keyword):
        # A keyword prints with its trailing colon, so it reads back.
        return f"{value}:"
    if isinstance(value, Char):
        return _char_literal(value.value)
    if isinstance(value, str):
        return _quote_string(value) if write else value
    if isinstance(value, MutableString):
        text = value.text
        return _quote_string(text) if write else text
    if isinstance(value, (int, float, Fraction)):
        return _number_literal(value)
    if isinstance(value, list):
        return "(" + " ".join(to_string(item, write) for item in value) + ")"
    if isinstance(value, Pair):
        return _pair_to_string(value, write)
    if isinstance(value, Vector):
        return "#(" + " ".join(to_string(item, write) for item in value.items) + ")"
    if isinstance(value, ByteVector):
        return "#u8(" + " ".join(str(byte) for byte in value.data) + ")"
    if isinstance(value, Tagged):
        # A tagged value prints as its constructor call: ``(define-variant
        # result (ok value) ...)`` makes ``(ok 3)``. It reads back as a *list*
        # of the same shape — ``tagged?`` is what tells the two apart, and
        # ``match`` accepts either.
        return "(" + " ".join(
            [str(value.tag), *(to_string(field, write) for field in value.fields)]
        ) + ")"
    if isinstance(value, Record):
        fields = " ".join(to_string(field, write) for field in value.fields)
        return f"#<record:{value.type_name}{' ' + fields if fields else ''}>"
    if isinstance(value, RecordType):
        return f"#<record-type {value.name}>"
    if isinstance(value, HashTable):
        return f"#<hash-table {len(value)}>"
    if value is EOF:
        return "#<eof>"
    if isinstance(value, Port):
        kind = (
            "input"
            if value.readable and not value.writable
            else "output"
            if value.writable and not value.readable
            else "input/output"
        )
        state = " (closed)" if value.closed else ""
        return f"#<{kind}-port {value.name}{state}>"
    if isinstance(value, ErrorObject):
        return f'#<error "{value.message}">'
    if isinstance(value, Values):
        inner = " ".join(to_string(item, write) for item in value)
        return f"#<values {inner}>"
    if isinstance(value, Closure):
        return f"#<closure {value.name}>"
    if isinstance(value, Macro):
        return f"#<macro {value.name}>"
    if isinstance(value, SyntaxRules):
        return f"#<syntax {value.name}>"
    if isinstance(value, Primitive):
        return f"#<primitive {value.name}>"
    # An opaque host value (a game, a Tx, a Result, ...).
    return f"#<{type(value).__name__}>"


#: Characters an identifier may begin with (R7RS §7.1.1, "initial" plus
#: "special initial").
_SYMBOL_INITIAL = frozenset("!$%&*/:<=>?^_~")

#: Characters that may appear after the first one ("subsequent" plus
#: "special subsequent").
_SYMBOL_SUBSEQUENT = _SYMBOL_INITIAL | frozenset("+-.@")

#: Identifiers that are only a plus, a minus, or three dots.
_PECULIAR_IDENTIFIERS = frozenset({"+", "-", "..."})


def _symbol_text(symbol: Symbol) -> str:
    """A symbol as text, quoted with ``|...|`` when it would not read back.

    A plain identifier is printed bare. Anything else — spaces, digits first,
    a leading ``#``, a character the reader would reject — is written between
    bars, with ``\\|`` and ``\\\\`` escaped, so ``write`` round-trips.
    """
    text = str(symbol)
    if text in _PECULIAR_IDENTIFIERS:
        return text
    if text and (text[0].isalpha() or text[0] in _SYMBOL_INITIAL):
        if all(ch.isalnum() or ch in _SYMBOL_SUBSEQUENT for ch in text[1:]):
            return text
    escaped = text.replace("\\", "\\\\").replace("|", "\\|")
    return f"|{escaped}|"


#: Characters with a reader name rather than a bare spelling.
_CHAR_NAMES = {
    " ": "space",
    "\n": "newline",
    "\t": "tab",
    "\r": "return",
    "\x00": "nul",
    "\x7f": "delete",
    "\x1b": "escape",
    "\x08": "backspace",
}


def _char_literal(ch: str) -> str:
    """``#\\a`` for a printable char, ``#\\space`` for a named one."""
    return "#\\" + _CHAR_NAMES.get(ch, ch)


def _pair_to_string(value: Pair, write: bool) -> str:
    """A (possibly dotted) pair chain, in the reader's own notation."""
    parts = []
    node: Any = value
    while isinstance(node, Pair):
        parts.append(to_string(node.car, write))
        node = node.cdr
    if is_nil(node):
        return "(" + " ".join(parts) + ")"
    return "(" + " ".join(parts) + " . " + to_string(node, write) + ")"


def _quote_string(text: str) -> str:
    escaped = (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'


def _number_literal(value: float | int | Fraction) -> str:
    """A number as text, with the written inexact specials spelled out.

    ``repr`` handles integers and finite floats; R7RS's ``inf``/``nan`` have
    their own literals (``+inf.0``), which the reader understands too. An
    exact rational prints ``p/q`` — reduced, sign on the numerator — which the
    reader reads back (R2 lands the literal side).
    """
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "+nan.0"
        if value == float("inf"):
            return "+inf.0"
        if value == float("-inf"):
            return "-inf.0"
    return repr(value)

