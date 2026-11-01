"""The reader — text in, forms out.

A Lisp reader is small because the syntax *is* the data: parentheses make
lists, and everything else is an atom. The sugar it understands::

    'x     ->  (quote x)
    `x     ->  (quasiquote x)
    ,x     ->  (unquote x)
    ,@x    ->  (unquote-splicing x)
    #(1 2) ->  a vector literal
    #\\a    ->  a character literal
    (a b . rest)  ->  a dotted pair chain
    #;form        ->  the form is read and thrown away
    #| ... |#     ->  a block comment

That expansion is the reason a macro can be a procedure over lists: by the
time anything is evaluated, quoting has already turned code into data.
"""
from __future__ import annotations

from typing import Iterator, List

from .errors import LispSyntaxError
from .types import (
    NIL,
    Symbol,
    from_cells,
    intern,
    intern_char,
    intern_keyword,
    make_list,
)

#: Characters that end an atom.
_DELIMITERS = set("()'`\",; \t\r\n[]")

#: Quote-sugar token -> the symbol it expands to.
_ABBREVIATIONS = {
    "'": "quote",
    "`": "quasiquote",
    ",": "unquote",
    ",@": "unquote-splicing",
}

#: Symbols the reader and evaluator share, interned once.
QUOTE = intern("quote")
QUASIQUOTE = intern("quasiquote")
UNQUOTE = intern("unquote")
UNQUOTE_SPLICING = intern("unquote-splicing")
DOT = intern(".")

#: The characters that have a written name in ``#\\name`` position.
_CHAR_NAMES = {
    "space": " ",
    "newline": "\n",
    "tab": "\t",
    "return": "\r",
    "nul": "\x00",
    "null": "\x00",
    "delete": "\x7f",
    "escape": "\x1b",
    "backspace": "\x08",
    "alarm": "\x07",
}

#: Numeric prefixes (``#x1f``, ``#b101``, ``#e1``, ``#i1``, ``#x#e10`` — the
#: prefixes may appear in either order; that is R7RS §7.1.1).
_RADIX = {"b": 2, "o": 8, "d": 10, "x": 16}

#: The recognitions the standard names for the special inexact literals.
_INEXACT_NAMES = {
    "+inf.0": float("inf"),
    "-inf.0": float("-inf"),
    "+nan.0": float("nan"),
    "-nan.0": float("nan"),
}

#: Sentinel from :func:`_number_from_literal` when the token is not a number.
NOT_A_NUMBER = object()

#: A character-literal token carries this marker so ``_atom`` knows.
_CHAR_MARK = "\x01"

#: A string token carries this marker so ``_atom`` knows.
_STRING_MARK = "\x00"

#: A ``|quoted symbol|`` token carries this marker so ``_atom`` knows; the
#: body is kept verbatim — case-sensitive, spaces allowed (R7RS §6.10).
_QUOTED_SYMBOL_MARK = "\x02"


def tokenize(text: str) -> Iterator[str]:
    """Split *text* into tokens: parentheses, sugar, and atoms."""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == ";":  # line comment
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("#|", i):  # block comment (nesting allowed)
            i = _skip_block_comment(text, i)
            continue
        if text.startswith("#;", i):  # datum comment: the next form is dropped
            yield "#;"
            i += 2
            continue
        if ch in "()[]":
            # Square brackets are list delimiters, exactly like parentheses
            # (SRFI 241 writes patterns with brackets); the reader maps them
            # to the same tokens.
            yield "(" if ch in "([" else ")"
            i += 1
            continue
        if text.startswith("#u8(", i):
            yield "#u8("
            i += 4
            continue
        if text.startswith("#(", i):
            yield "#("
            i += 2
            continue
        if text.startswith("#\\", i):
            token, i = _scan_char(text, i)
            yield token
            continue
        if ch == "," and i + 1 < n and text[i + 1] == "@":
            yield ",@"
            i += 2
            continue
        if ch in "'`,":
            yield ch
            i += 1
            continue
        if ch == '"':
            token, i = _scan_string(text, i)
            yield token
            continue
        if ch == "|":  # |quoted symbol| — unusual characters, case preserved
            token, i = _scan_quoted_symbol(text, i)
            yield token
            continue
        if text.startswith("#!", i):
            if text.startswith("#!fold-case", i):
                yield "#!fold-case"
                i += len("#!fold-case")
                continue
            if text.startswith("#!no-fold-case", i):
                yield "#!no-fold-case"
                i += len("#!no-fold-case")
                continue
            # An unknown directive reads as an atom; there is nothing to fold.

        # An atom: run until a delimiter.
        start = i
        while i < n and text[i] not in _DELIMITERS:
            i += 1
        yield text[start:i]


def _skip_block_comment(text: str, i: int) -> int:
    """Consume ``#| ... |#`` starting at *i*; return the index past it."""
    depth = 1
    i += 2
    n = len(text)
    while i < n:
        if text.startswith("#|", i):
            depth += 1
            i += 2
        elif text.startswith("|#", i):
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    raise LispSyntaxError("unterminated block comment")


def _number_from_literal(token: str):
    """A numeric literal, or :data:`NOT_A_NUMBER` if *token* is not one.

    Supports the R7RS radix and exactness prefixes in either order
    (``#x1f``/``#b101``/``#e1``/``#i1``/``#e#x10``), and the written inexact
    specials ``+inf.0``/``-inf.0``/``+nan.0``/``-nan.0``. Dotted rationals
    (``1/3``) are outside the numeric tower; those tokens stay symbols.
    """
    if token in _INEXACT_NAMES:
        return _INEXACT_NAMES[token]
    if not token.startswith("#"):
        plain = _plain_number(token)
        return NOT_A_NUMBER if plain is None else plain
    radix, exactness = 10, None
    rest = token[1:]
    consumed = False
    for _ in range(4):
        if rest.startswith("#"):  # ``#e#x10`` — prefixes may be '#' separated
            rest = rest[1:]
            continue
        head = rest[:1].lower()
        if head in _RADIX:
            radix, rest = _RADIX[head], rest[1:]
            consumed = True
        elif head in ("e", "i"):
            exactness, rest = head, rest[1:]
            consumed = True
        else:
            break
    if not rest or not consumed:  # not a numeric form (``#foo`` stays a symbol)
        return NOT_A_NUMBER
    if not rest:
        raise LispSyntaxError(f"bad number literal: {token}")
    if radix != 10:
        try:
            return int(rest, radix)
        except ValueError:
            raise LispSyntaxError(f"bad number literal: {token}") from None
    value = _plain_number(rest)
    if value is None:
        return NOT_A_NUMBER
    if exactness == "e":
        return int(value) if isinstance(value, float) and value.is_integer() else value
    if exactness == "i":
        return float(value)
    return value


def _plain_number(token: str):
    """``42`` -> ``42``, ``3.5`` -> ``3.5``, anything else -> ``None``.

    ``1/3`` and friends are intentionally *not* numbers here: the tower has no
    exact rationals, so such a token falls through to the symbol path and the
    deviation stays loud instead of silently wrong.
    """
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return None


def _fold_symbol(token: str) -> str:
    """Fold-case an identifier token; never a number, never a ``#``-form."""
    if not token or token[0].isdigit() or token.startswith("#"):
        return token
    if _plain_number(token) is not None:
        return token
    return token.lower()


def _scan_quoted_symbol(text: str, i: int) -> tuple[str, int]:
    """Read ``|any characters|`` at *i*; the body is kept verbatim.

    ``\\|`` and ``\\\\`` stand for a bar and a backslash inside the bars, and
    ``\\xHH;`` is a hex scalar escape (R7RS §6.10) — the same escapes the
    printer emits when a symbol needs quoting.
    """
    i += 1
    body: List[str] = []
    n = len(text)
    while True:
        if i >= n:
            raise LispSyntaxError("unterminated |quoted symbol|")
        ch = text[i]
        if ch == "|":
            return _QUOTED_SYMBOL_MARK + "".join(body), i + 1
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "x":
                j = i + 2
                while j < n and text[j] != ";":
                    j += 1
                if j >= n:
                    raise LispSyntaxError("unterminated \\x escape in |symbol|")
                try:
                    body.append(chr(int(text[i + 2 : j], 16)))
                except ValueError:
                    raise LispSyntaxError("bad \\x escape in |symbol|") from None
                i = j + 1
                continue
            body.append({"|": "|", "\\": "\\"}.get(nxt, nxt))
            i += 2
            continue
        body.append(ch)
        i += 1


def _scan_char(text: str, i: int) -> tuple[str, int]:
    """Read ``#\\a`` / ``#\\space`` / ``#\\x41`` at *i*."""
    i += 2  # skip the ``#\``
    if i >= len(text):
        raise LispSyntaxError("nothing follows #\\")
    first = text[i]
    if first.isalpha():
        j = i
        while j < len(text) and (text[j].isalnum() or text[j] == "-"):
            j += 1
        name = text[i:j]
        return _CHAR_MARK + _char_value(name), j
    # Any other single character is itself — including space and punctuation.
    return _CHAR_MARK + first, i + 1


def _char_value(name: str) -> str:
    """A ``#\\`` name as its one-character string."""
    if name in _CHAR_NAMES:
        return _CHAR_NAMES[name]
    if name == "x":
        return "x"
    if len(name) > 1 and name[0] == "x":
        try:
            return chr(int(name[1:], 16))
        except ValueError:
            raise LispSyntaxError(f"bad hex character literal: #\\{name}") from None
    if len(name) > 1:
        raise LispSyntaxError(f"unknown character name: #\\{name}")
    return name


def _scan_string(text: str, i: int) -> tuple[str, int]:
    """Read a string literal starting at the opening quote; keep it a ``str``."""
    i += 1  # skip opening quote
    body: List[str] = []
    n = len(text)
    while True:
        if i >= n:
            raise LispSyntaxError("unterminated string literal")
        ch = text[i]
        if ch == "\\":
            if i + 1 >= n:
                raise LispSyntaxError("unterminated escape in string")
            nxt = text[i + 1]
            if nxt == "x":  # \xNN; — a hex escape, terminated by ;
                j = i + 2
                while j < n and text[j] != ";":
                    j += 1
                if j >= n:
                    raise LispSyntaxError("unterminated \\x escape")
                try:
                    body.append(chr(int(text[i + 2 : j], 16)))
                except ValueError:
                    raise LispSyntaxError("bad \\x escape") from None
                i = j + 1
                continue
            if nxt in "\r\n":  # line continuation: \\ + <newline> + whitespace
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                i = j
                continue
            body.append(
                {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    "a": "\x07",
                    "b": "\x08",
                    "|": "|",
                    "0": "\x00",
                    '"': '"',
                    "\\": "\\",
                }.get(nxt, nxt)
            )
            i += 2
            continue
        if ch == '"':
            i += 1
            break
        body.append(ch)
        i += 1
    # The token carries a leading marker so ``read_atom`` knows it is text.
    return _STRING_MARK + "".join(body), i


def _atom(token: str):
    """An atom token as a value: bool, number, string, char, or symbol."""
    if token.startswith(_STRING_MARK):
        return token[1:]
    if token.startswith(_CHAR_MARK):
        return intern_char(token[1:])
    if token.startswith(_QUOTED_SYMBOL_MARK):
        return intern(token[len(_QUOTED_SYMBOL_MARK) :])
    if token == "#t":
        return True
    if token == "#f":
        return False
    value = _number_from_literal(token)
    if value is not NOT_A_NUMBER:
        return value
    # A keyword: `foo:` is one, `:foo` is not (a leading colon reads as an
    # ordinary symbol), and a lone `:` is not either.
    if token.endswith(":") and len(token) > 1 and not token.startswith(("#", "|")):
        return intern_keyword(token[:-1])
    return intern(token)


class Reader:
    """A pull-based recursive-descent parser over a token list."""

    def __init__(self, text: str) -> None:
        self.tokens = list(tokenize(text))
        self.pos = 0
        #: ``#!fold-case`` / ``#!no-fold-case``; R7RS's default is off.
        self.fold_case = False

    def at_end(self) -> bool:
        return self.pos >= len(self.tokens)

    def _skip_noise(self) -> None:
        """Consume ``#;`` datum comments and ``#!`` case directives."""
        while not self.at_end():
            token = self.tokens[self.pos]
            if token == "#;":
                self.pos += 1
                self.read_form()
            elif token == "#!fold-case":
                self.fold_case = True
                self.pos += 1
            elif token == "#!no-fold-case":
                self.fold_case = False
                self.pos += 1
            else:
                break

    def read_form(self):
        self._skip_noise()
        if self.at_end():
            raise LispSyntaxError("unexpected end of input")
        token = self.tokens[self.pos]
        self.pos += 1
        if self.fold_case and not token.startswith(
            (_STRING_MARK, _CHAR_MARK, _QUOTED_SYMBOL_MARK)
        ):
            token = _fold_symbol(token)

        if token == "(":
            return self._read_list()
        if token == "#(":
            return self._read_vector()
        if token == "#u8(":
            return self._read_bytevector()
        if token == ")":
            raise LispSyntaxError("unexpected )")
        if token == ")":
            raise LispSyntaxError("unexpected )")
        if token in _ABBREVIATIONS:
            name = _ABBREVIATIONS[token]
            if self.at_end():
                raise LispSyntaxError(f"nothing follows {token!r}")
            return [intern(name), self.read_form()]
        return _atom(token)

    def _read_vector(self):
        from .types import Vector

        items = []
        while True:
            self._skip_noise()
            if self.at_end():
                raise LispSyntaxError("missing )")
            if self.tokens[self.pos] == ")":
                self.pos += 1
                break
            items.append(self.read_form())
        return Vector(items)

    def _read_bytevector(self):
        from .types import ByteVector

        items = []
        while True:
            self._skip_noise()
            if self.at_end():
                raise LispSyntaxError("missing )")
            if self.tokens[self.pos] == ")":
                self.pos += 1
                break
            value = self.read_form()
            if not isinstance(value, int) or isinstance(value, bool):
                raise LispSyntaxError(
                    f"bytevector: expected an exact integer, got {value!r}"
                )
            if not 0 <= value <= 255:
                raise LispSyntaxError(f"bytevector: {value} is outside 0..255")
            items.append(value)
        return ByteVector(items)

    def _read_list(self):
        items = []
        while True:
            self._skip_noise()
            if self.at_end():
                raise LispSyntaxError("missing )")
            token = self.tokens[self.pos]
            if token == ")":
                self.pos += 1
                break
            if token == ".":
                # A dotted tail: exactly one form follows, then the close paren.
                self.pos += 1
                if self.at_end() or self.tokens[self.pos] == ")":
                    raise LispSyntaxError("'.' must be followed by one form")
                tail = self.read_form()
                self._skip_noise()
                if self.at_end() or self.tokens[self.pos] != ")":
                    raise LispSyntaxError("'.' must precede the final form")
                self.pos += 1
                return from_cells(items, tail)
            items.append(self.read_form())
        return make_list(items)

    def read_all(self) -> list:
        """Every form in the text, in order."""
        forms = []
        while True:
            self._skip_noise()
            if self.at_end():
                break
            forms.append(self.read_form())
        return forms


#: The ``#!`` case-folding directives — the only ``#!`` lines with a meaning
#: of their own. Any other ``#!`` line at the head of a text is a shebang.
_CASE_DIRECTIVES = ("#!fold-case", "#!no-fold-case")


def _strip_shebang(text: str) -> str:
    """Drop a leading ``#!`` interpreter line — a shebang, gosh-style.

    ``#!/usr/bin/env shs`` cannot parse as anything else, so a text that
    *starts* with such a line is an executable script, and the line is
    scaffolding, not Scheme: skip it. The case-folding directives are exempt
    (they are meaningful ``#!`` forms, and may share their line with the code
    that follows), and a shebang may be *followed* by one, so keep skipping
    until the first directive or a non-``#!`` line.
    """
    while text.startswith("#!"):
        first, _, rest = text.partition("\n")
        if first.split(None, 1)[0] in _CASE_DIRECTIVES:
            break
        text = rest
    return text


def read_all(text: str) -> list:
    """Parse *text* into a list of forms."""
    return Reader(_strip_shebang(text)).read_all()


def read_one(text: str):
    """Parse exactly one form; a trailing form is a syntax error."""
    reader = Reader(text)
    form = reader.read_form()
    if not reader.at_end():
        raise LispSyntaxError("trailing data after form")
    return form


#: Characters that end an unquoted atom.
_ATOM_DELIMITERS = set("()'`\",; \t\r\n|[]")


def _skip_white_and_comments(text: str, i: int) -> int:
    """Skip whitespace, ``;`` lines, ``#| |#`` blocks, and ``#;`` data."""
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
            continue
        if ch == ";":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("#|", i):
            i = _skip_block_comment(text, i)
            continue
        if text.startswith("#;", i):
            i = _skip_white_and_comments(text, i + 2)
            _, i = _datum_end(text, i)
            continue
        break
    return i


def _datum_end(text: str, i: int) -> tuple[int, int]:
    """The end index of the one datum starting at *i*.

    Used by ``read`` on a port: it lets the reader consume exactly one datum
    and leave the rest of the stream untouched.
    """
    i = _skip_white_and_comments(text, i)
    n = len(text)
    if i >= n:
        raise LispSyntaxError("unexpected end of input")
    ch = text[i]
    if ch in "'`,":
        if text.startswith(",@", i):
            i += 1
        return _datum_end(text, i + 1)
    if ch == "(":
        return _balanced_end(text, i), 0
    if text.startswith("#(", i):
        return _balanced_end(text, i + 1), 0
    if text.startswith("#u8(", i):
        return _balanced_end(text, i + 3), 0
    if ch == '"':
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == '"':
                return j + 1, 0
            j += 1
        raise LispSyntaxError("unterminated string literal")
    if text.startswith("#\\", i):
        j = i + 2
        if j < n and text[j].isalpha():
            while j < n and (text[j].isalnum() or text[j] == "-"):
                j += 1
        else:
            j += 1
        return j, 0
    if ch == "|":
        j = i + 1
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == "|":
                return j + 1, 0
            j += 1
        raise LispSyntaxError("unterminated |quoted symbol|")
    j = i
    while j < n and text[j] not in _ATOM_DELIMITERS:
        j += 1
    return j, 0


def _balanced_end(text: str, i: int) -> int:
    """The index just past the ``)`` matching the ``(`` at *i*."""
    depth = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == ";":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("#|", i):
            i = _skip_block_comment(text, i)
            continue
        if ch in "\"'`,":
            i += 1
            continue
        if text.startswith("#\\", i):
            i, _ = _datum_end(text, i)
            continue
        if ch == "|":
            i, _ = _datum_end(text, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise LispSyntaxError("missing )")


def read_one_at(text: str, start: int = 0) -> tuple[Any, int]:
    """Read the first datum at or after *start*, and the index after it.

    Raises :class:`LispSyntaxError` on bad input. The caller decides what an
    empty tail means (``read`` returns the eof object).
    """
    i = _skip_white_and_comments(text, start)
    if i >= len(text):
        raise LispSyntaxError("unexpected end of input")
    end, _ = _datum_end(text, i)
    return read_one(text[i:end]), end


# ``Symbol`` and ``NIL`` are re-exported for callers that only import the reader.
__all__ = [
    "Reader",
    "read_all",
    "read_one",
    "read_one_at",
    "tokenize",
    "Symbol",
    "NIL",
]
