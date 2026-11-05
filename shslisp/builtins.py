"""The core library — the primitives a Lisp cannot define for itself.

Split in two on purpose:

* **Pure functions** (``+``, ``car``, ``map`` …) are the language's algebra.
* **A few host hooks** (``display``, ``error``, ``eval`` — and ``load``,
  which lives next door in :mod:`shslisp.loader` because resolution is a policy)
  are the deliberate holes where a program touches the outside world. Keeping
  the holes few and named is what lets the rest of a program be reasoned about
  as pure.

Nothing here is a special form; every name in this module is a first-class
value. ``(define + 3)`` would even work — shadowing a builtin is allowed,
because a lexical scope that can be shadowed is a lexical scope you can
reason about.
"""
from __future__ import annotations

import io
import cmath
import math
import os
import sys
import time
import unicodedata
from fractions import Fraction
from typing import Any, Callable, Iterable, Optional, TextIO

from .env import Environment
from .errors import (
    ContinuationJump,
    FileError,
    LispError,
    LispRaise,
    LispSyntaxError,
    LispTypeError,
    ReadError,
)
from .features import feature_symbols
from .libraries import library_name
from .reader import NOT_A_NUMBER, _number_from_literal
from .evaluator import (
    apply_procedure,
    equal,
    evaluate,
    macroexpand,
    variant_of,
    variant_tags,
)
from .printer import to_string
from .reader import read_all
from .types import (
    NIL,
    ByteVector,
    Char,
    Closure,
    Complex,
    EOF,
    ErrorObject,
    HashTable,
    Keyword,
    MutableString,
    Pair,
    Port,
    Primitive,
    Symbol,
    Tagged,
    Values,
    Vector,
    from_cells,
    intern,
    intern_keyword,
    is_char,
    is_error_object,
    is_keyword,
    is_nil,
    is_pair,
    is_procedure,
    is_symbol,
    is_tagged,
    is_true,
    list_to_python,
    make_list,
    make_tagged,
    to_cells,
)

#: The numeric tower's Python types: exact integers, exact rationals
#: (:class:`fractions.Fraction` — always reduced, and normalized to ``int``
#: whenever the denominator is 1), exact complex pairs (:class:`Complex` —
#: C1), and the inexact half (``float`` reals; ``complex`` is what inexact
#: complex arithmetic answers).
Number = (int, float, Fraction, Complex, complex)


def install_core(env: Environment, out: Optional[TextIO] = None) -> Environment:
    """Bind every core primitive into *env* (returned for convenience)."""
    out = out if out is not None else sys.stdout

    def define(name: str, fn: Callable[..., Any]) -> None:
        env.define(intern(name), Primitive(name, fn))

    # -- numbers ------------------------------------------------------------ #
    # Every arithmetic primitive gates its arguments through
    # `_expect_number`, so a boolean can never masquerade as a number here:
    # Python's `bool` subclasses `int`, and `(+ #t 1)` would otherwise be 2
    # while `number?` says `#f`. The gate is the difference between the two
    # answers.
    define("+", lambda *xs: _normalize_rational(
        sum((_expect_number(x, "+") for x in _complex_shim(xs)), 0)))
    define("-", _sub)
    define("*", lambda *xs: _normalize_rational(
        _product(_complex_shim(xs))))
    define("/", _div)
    define("modulo", _modulo)
    define("quotient", _quotient)
    define("remainder", _remainder)
    define("abs", lambda x: _normalize_rational(abs(_expect_number(x, "abs"))))
    define("min", _min)
    define("max", _max)
    define("expt", _expt)
    define("sqrt", _sqrt)
    define("floor", _floor)
    define("ceiling", _ceiling)
    define("truncate", _truncate)
    define("round", _round)
    define("gcd", lambda *xs: _gcd(xs))
    define("lcm", lambda *xs: _lcm(xs))

    # -- the inexact library (A7); C2 makes it complex-aware ----------------- #
    define("finite?", _finite_p)
    define("infinite?", _infinite_p)
    define("nan?", _nan_p)
    define("exp", lambda x: _math1("exp", math.exp, cmath.exp, x))
    define("log", _log)
    define("sin", lambda x: _math1("sin", math.sin, cmath.sin, x))
    define("cos", lambda x: _math1("cos", math.cos, cmath.cos, x))
    define("tan", lambda x: _math1("tan", math.tan, cmath.tan, x))
    define("asin", lambda x: _math1("asin", math.asin, cmath.asin, x))
    define("acos", lambda x: _math1("acos", math.acos, cmath.acos, x))
    define("atan", _atan)
    # -- the complex tower, polar half (C2) ---------------------------------- #
    define("magnitude", lambda x: _normalize_rational(
        abs(_expect_number(x, "magnitude"))))
    define("angle", _angle_prim)
    define("make-polar", _make_polar)

    define("=", lambda *xs: _chain(xs, lambda a, b: a == b))
    define("<", lambda *xs: _chain(xs, lambda a, b: a < b, ordered=True))
    define(">", lambda *xs: _chain(xs, lambda a, b: a > b, ordered=True))
    define("<=", lambda *xs: _chain(xs, lambda a, b: a <= b, ordered=True))
    define(">=", lambda *xs: _chain(xs, lambda a, b: a >= b, ordered=True))

    define("number?", lambda x: isinstance(x, Number) and not isinstance(x, bool))
    define("integer?", _is_integer_value)
    # The tower's exactness is a type question: an exact number is an ``int``,
    # a ``Fraction``, or an exact ``Complex`` (C1); an inexact one is a
    # ``float`` or a Python ``complex``.
    define("exact?", lambda x: (
        (isinstance(x, int) and not isinstance(x, bool))
        or isinstance(x, (Fraction, Complex))))
    define("inexact?", lambda x: isinstance(x, (float, complex)))
    define("exact-integer?", lambda x: isinstance(x, int) and not isinstance(x, bool))
    define("rational?", _rational_p)
    define("real?", _real_p)
    define("complex?", lambda x: isinstance(x, Number) and not isinstance(x, bool))
    define("exact", _exact)
    define("inexact", _inexact)
    # The R5RS spellings (A6/A7): the same two conversions under their
    # historical names, so the optional `(scheme r5rs)` library imports whole.
    # One place owns the semantics; these are aliases, not re-implementations.
    define("exact->inexact", _inexact)
    define("inexact->exact", _exact)
    define("square", lambda x: _normalize_rational(
        _expect_number(x, "square") ** 2))
    define("exact-integer-sqrt", _exact_integer_sqrt)
    define("numerator", _numerator)
    define("denominator", _denominator)
    define("rationalize", _rationalize)
    # -- the complex tower, first stage (C1) --------------------------------- #
    # The rectangular accessors: the constructors and predicates the rest of
    # the complex work hangs off. C2 lands make-polar/magnitude/angle and the
    # exact sqrt of negatives; C3 lands the reader and printer round-trip.
    define("make-rectangular", _make_rectangular)
    define("real-part", _real_part)
    define("imag-part", _imag_part)
    define("floor-quotient", lambda a, b: _floor_quotient(a, b))
    define("floor-remainder", lambda a, b: _floor_remainder(a, b))
    define("floor/", lambda a, b: Values((_floor_quotient(a, b), _floor_remainder(a, b))))
    define("truncate-quotient", lambda a, b: _quotient(a, b))
    define("truncate-remainder", lambda a, b: _remainder(a, b))
    define("truncate/", lambda a, b: Values((_quotient(a, b), _remainder(a, b))))

    # -- equality and logic ------------------------------------------------- #
    define("equal?", equal)
    define("eq?", _eq)
    define("eqv?", _eqv)
    define("not", lambda x: not is_true(x))
    define("boolean?", lambda x: isinstance(x, bool))
    define("boolean=?", lambda *xs: _chain(xs, lambda a, b: a is b))
    define("void", lambda *_: NIL)

    # -- pairs and lists ---------------------------------------------------- #
    define("cons", _cons)
    define("car", _car)
    define("cdr", _cdr)
    define("caar", lambda xs: _car(_car(xs)))
    define("cadr", lambda xs: _car(_cdr(xs)))
    define("cddr", lambda xs: _cdr(_cdr(xs)))
    define("cdar", lambda xs: _cdr(_car(xs)))
    for _cxr in (
        "caaaar caaadr caaar caadar caaddr caadr cadaar cadadr cadar caddar "
        "cadddr caddr cdaaar cdaadr cdaar cdadar cdaddr cdadr cddaar cddadr "
        "cddar cdddar cddddr cdddr"
    ).split():
        define(_cxr, _make_cxr(_cxr))
    define("list", lambda *xs: make_list(xs))
    define("length", _length)
    define("append", _append)
    define("reverse", lambda xs: make_list(reversed(list_to_python(xs))))
    define("list-ref", _list_ref)
    define("list-tail", _list_tail)
    define("take", _take)
    define("drop", _drop)
    define("list?", lambda x: is_nil(x) or isinstance(x, list))
    define("null?", is_nil)
    define("pair?", is_pair)
    define("list-set!", _list_set)
    define("set-car!", _set_car)
    define("set-cdr!", _set_cdr)
    define("list-copy", lambda xs: make_list(to_cells(xs)) if not is_nil(xs) else NIL)
    define("make-list", _make_list)
    define("member", _member_pair)
    define("member?", lambda x, xs: is_true(_member(x, xs)))
    define("memq", lambda x, xs: _memq(x, xs, _eq))
    define("memv", lambda x, xs: _memq(x, xs, _eqv))
    define("assoc", _assoc)
    define("assq", lambda key, alist: _assoc_with(key, alist, _eq))
    define("assv", lambda key, alist: _assoc_with(key, alist, _eqv))

    define("map", _map)
    define("filter", lambda f, xs: make_list(x for x in list_to_python(xs) if is_true(apply_procedure(f, [x]))))
    define("foldl", _foldl)
    define("foldr", _foldr)
    define("for-each", _for_each)
    define("range", _range)
    define("sort", _sort)

    # -- characters --------------------------------------------------------- #
    define("char?", is_char)
    define("char->integer", lambda c: ord(_expect_char(c)))
    define("integer->char", lambda n: _char(chr(n)))
    define("char=?", lambda *cs: _char_chain(cs, lambda a, b: a == b))
    define("char<?", lambda *cs: _char_chain(cs, lambda a, b: a < b))
    define("char>?", lambda *cs: _char_chain(cs, lambda a, b: a > b))
    define("char<=?", lambda *cs: _char_chain(cs, lambda a, b: a <= b))
    define("char>=?", lambda *cs: _char_chain(cs, lambda a, b: a >= b))
    define("char-alphabetic?", lambda c: _expect_char(c).isalpha())
    define("char-numeric?", lambda c: _expect_char(c).isdigit())
    define("char-whitespace?", lambda c: _expect_char(c).isspace())
    define("char-upper-case?", lambda c: _expect_char(c).isupper())
    define("char-lower-case?", lambda c: _expect_char(c).islower())
    define("char-upcase", lambda c: _char(_expect_char(c).upper()))
    define("char-downcase", lambda c: _char(_expect_char(c).lower()))
    define("char-foldcase", lambda c: _char(_fold_char(_expect_char(c))))
    define("char-ci=?", lambda *cs: _char_ci_chain(cs, lambda a, b: a == b))
    define("char-ci<?", lambda *cs: _char_ci_chain(cs, lambda a, b: a < b))
    define("char-ci>?", lambda *cs: _char_ci_chain(cs, lambda a, b: a > b))
    define("char-ci<=?", lambda *cs: _char_ci_chain(cs, lambda a, b: a <= b))
    define("char-ci>=?", lambda *cs: _char_ci_chain(cs, lambda a, b: a >= b))
    define("digit-value", _digit_value)

    # -- symbols and strings ------------------------------------------------ #
    define("symbol?", is_symbol)
    define(
        "string?",
        lambda x: (
            isinstance(x, str)
            and not isinstance(x, (Symbol, Keyword))
        )
        or isinstance(x, MutableString),
    )
    define("keyword?", is_keyword)
    define("keyword->string", lambda kw: str(_expect_keyword(kw)))
    define("string->keyword", lambda s: intern_keyword(_expect_string(s)))
    define("procedure?", is_procedure)
    define("procedure-arity", _procedure_arity)
    define("symbol->string", str)
    define("string->symbol", lambda s: intern(_expect_string(s)))
    define("symbol=?", lambda *ss: _symbol_chain(ss))
    define("string", lambda *cs: "".join(_expect_char(c) for c in cs))
    define("string-append", lambda *xs: "".join(_expect_string(x) for x in xs))
    define("string-length", lambda s: len(_expect_string(s)))
    define("string=?", lambda a, b: _expect_string(a) == _expect_string(b))
    define("string<?", lambda a, b: _expect_string(a) < _expect_string(b))
    define("string>?", lambda a, b: _expect_string(a) > _expect_string(b))
    define("string<=?", lambda a, b: _expect_string(a) <= _expect_string(b))
    define("string>=?", lambda a, b: _expect_string(a) >= _expect_string(b))
    define("string-ref", _string_ref)
    define("string-copy", lambda s: MutableString(_expect_string(s)))
    define("make-string", _make_string)
    define("substring", _substring)
    define("string-set!", _string_set)
    define("string-fill!", _string_fill)
    define("string-copy!", _string_copy_into)
    define("string->number", _string_to_number)
    define("number->string", _number_to_string)
    define("to-string", lambda x: to_string(x, write=False))
    define("write-to-string", lambda x: to_string(x, write=True))
    define("string->list", lambda s: make_list(_char(c) for c in _expect_string(s)))
    define("list->string", _list_to_string)
    define("string-map", _string_map)
    define("string-for-each", _string_for_each)
    define("string-upcase", lambda s: _expect_string(s).upper())
    define("string-downcase", lambda s: _expect_string(s).lower())
    define("string-foldcase", lambda s: _expect_string(s).casefold())
    define("string-ci=?", lambda *ss: _string_ci_chain(ss, lambda a, b: a == b))
    define("string-ci<?", lambda *ss: _string_ci_chain(ss, lambda a, b: a < b))
    define("string-ci>?", lambda *ss: _string_ci_chain(ss, lambda a, b: a > b))
    define("string-ci<=?", lambda *ss: _string_ci_chain(ss, lambda a, b: a <= b))
    define("string-ci>=?", lambda *ss: _string_ci_chain(ss, lambda a, b: a >= b))
    define("string-trim", lambda s: _expect_string(s).strip())
    define("string-split", _string_split)
    define("string-join", _string_join)
    define("string-contains?", lambda s, sub: _expect_string(sub) in _expect_string(s))

    # -- vectors ------------------------------------------------------------ #
    define("vector", lambda *xs: Vector(xs))
    define("make-vector", _make_vector)
    define("vector?", lambda x: isinstance(x, Vector))
    define("vector-length", lambda v: len(_expect_vector(v)))
    define("vector-ref", _vector_ref)
    define("vector-set!", _vector_set)
    define("vector-fill!", _vector_fill)
    define("vector-copy", _vector_copy)
    define("vector-copy!", _vector_copy_into)
    define("vector-append", _vector_append)
    define("vector->list", lambda v: make_list(_expect_vector(v).items))
    define("list->vector", lambda xs: Vector(list_to_python(xs)))
    define("vector->string", lambda v: "".join(_expect_char(c) for c in _expect_vector(v).items))
    define("string->vector", lambda s: Vector([_char(c) for c in _expect_string(s)]))
    define("vector-map", _vector_map)
    define("vector-for-each", _vector_for_each)

    # -- bytevectors -------------------------------------------------------- #
    define("bytevector?", lambda x: isinstance(x, ByteVector))
    define("make-bytevector", _make_bytevector)
    define("bytevector", _bytevector)
    define("bytevector-length", lambda bv: len(_expect_bytevector(bv, "bytevector-length")))
    define("bytevector-u8-ref", _bytevector_u8_ref)
    define("bytevector-u8-set!", _bytevector_u8_set)
    define("bytevector-copy", _bytevector_copy)
    define("bytevector-copy!", _bytevector_copy_into)
    define("bytevector-append", _bytevector_append)
    define("utf8->string", _utf8_to_string)
    define("string->utf8", _string_to_utf8)

    # -- hash tables -------------------------------------------------------- #
    define("make-hash-table", lambda *_: HashTable())
    define("hash-table?", lambda x: isinstance(x, HashTable))
    define("hash-table-set!", lambda h, k, v: _hash_set(h, k, v))
    define("hash-table-ref", _hash_ref)
    define("hash-table-ref/default", lambda h, k, d: _expect_hash(h).get(k, d))
    define("hash-table-has-key?", lambda h, k: _expect_hash(h).has(k))
    define("hash-table-delete!", lambda h, k: _expect_hash(h).delete(k))
    define("hash-table-count", lambda h: len(_expect_hash(h)))
    define("hash-table-keys", lambda h: make_list(_expect_hash(h).keys()))
    define("hash-table-values", lambda h: make_list(_expect_hash(h).values()))
    define("hash-table-clear!", lambda h: _hash_clear(h))
    define("hash-table->alist", lambda h: make_list([
        make_list([k, v]) for k, v in _expect_hash(h).entries()
    ]))
    define("hash-table-update!", _hash_update)

    # -- tagged values (the carrier `match` dispatches on) ------------------ #
    define("tag", lambda tag, *fields: _make_tag(tag, fields))
    define("tagged?", is_tagged)
    define("tag-of", _tag_of)
    define("tag-fields", _tag_fields)
    define("variant-tags", lambda name: _variant_tags(name))
    define("variant-of", lambda tag: _variant_of(tag))

    # -- conditions and multiple values ------------------------------------- #
    define("raise", lambda value: _raise(value))
    define("raise-continuable", lambda value: _raise_continuable(value))
    define("error-object?", is_error_object)
    define("error-object-message", lambda e: _error_slot(e, "message"))
    define("error-object-irritants", lambda e: make_list(_error_slot(e, "irritants")))
    define("with-exception-handler", _with_exception_handler)
    define("dynamic-wind", _dynamic_wind)
    define("values", _values)
    define("call-with-values", _call_with_values)

    # -- continuations ------------------------------------------------------ #
    define("call/cc", _call_cc)
    define("call-with-current-continuation", _call_cc)
    define("call-with-escape-continuation", _call_cc)

    # -- control over the host --------------------------------------------- #
    define("apply", _apply)
    define("eval", lambda form, target=None: evaluate(
        form, env if target is None else _expect_environment(target, "eval")))
    define("interaction-environment", lambda: env)
    define("environment", lambda *specs: _environment(env, specs))

    def _r5rs_version(version: Any, who: str) -> None:
        if version != 5:
            raise LispError(f"{who}: only version 5 is defined (got {version})")

    def null_environment(version: Any) -> Environment:
        """``(null-environment 5)`` — syntax only: a root scope with no
        bindings, where the special forms still work and nothing else does."""
        _r5rs_version(version, "null-environment")
        return Environment()

    def scheme_report_environment(version: Any) -> Environment:
        """``(scheme-report-environment 5)`` — the R5RS surface as this
        interpreter spells it: the ``(scheme r5rs)`` exports in a root scope
        (so a name outside that surface is unbound, as the report intends)."""
        _r5rs_version(version, "scheme-report-environment")
        from .library import environment_from_specs

        return environment_from_specs(env, (read_all("(scheme r5rs)")[0],))

    define("null-environment", null_environment)
    define("scheme-report-environment", scheme_report_environment)
    define("features", lambda: make_list(feature_symbols()))
    # R7RS ``read-string`` reads characters; the datum-from-text convenience
    # lives on under its own name (and is not part of ``(scheme base)``).
    define(
        "read-string",
        lambda count, *rest: _read_string(
            count, destination(rest, "current-input-port", standard_in)
        ),
    )
    define("read-from-string", lambda text: _read_first(text))

    # -- macros, from the outside ------------------------------------------- #
    #
    # A macro author's microscope: `macroexpand-1` takes one step, `macroexpand`
    # keeps going while the head still names a macro. Both hand back the *form*,
    # so the answer prints as code and can be fed straight back to `eval`.
    define("macroexpand-1", lambda form: macroexpand(form, env, once=True))
    define("macroexpand", lambda form: macroexpand(form, env))

    # -- ports and I/O ------------------------------------------------------ #
    #
    # The three standard ports are *values*; the `current-*-port` procedures
    # that a program parameterizes live in the prelude, on top of these. So the
    # host hook is one directional: primitives write to a port they are handed,
    # and "the current port" is a Lisp-level dynamic binding, not host state.
    standard_in = Port(sys.stdin, readable=True, name="<stdin>")
    standard_out = Port(out, writable=True, name="<stdout>")
    standard_err = Port(sys.stderr, writable=True, name="<stderr>")

    def current_port(name: str, fallback: Port) -> Port:
        """The parameter ``name`` (prelude) if bound here, else *fallback*."""
        found = env.find(intern(name))
        if found is None:
            return fallback
        return apply_procedure(env.lookup(intern(name)), [])

    def destination(rest: Any, name: str, fallback: Port) -> Any:
        if rest and not is_nil(rest[0]):
            return rest[0]
        return current_port(name, fallback)

    define("standard-input-port", lambda: standard_in)
    define("standard-output-port", lambda: standard_out)
    define("standard-error-port", lambda: standard_err)
    define("port?", lambda x: isinstance(x, Port))
    define("input-port?", lambda x: isinstance(x, Port) and x.readable)
    define("output-port?", lambda x: isinstance(x, Port) and x.writable)
    define("textual-port?", lambda x: isinstance(x, Port) and not x.binary)
    define("binary-port?", lambda x: isinstance(x, Port) and x.binary)
    define("input-port-open?", lambda x: isinstance(x, Port) and x.readable and not x.closed)
    define("output-port-open?", lambda x: isinstance(x, Port) and x.writable and not x.closed)
    define("close-port", _close_port)
    define("close-input-port", lambda p: _close_direction(p, "close-input-port", True))
    define("close-output-port", lambda p: _close_direction(p, "close-output-port", False))
    define("call-with-port", _call_with_port)
    define("flush-output-port", _flush_port)
    define("open-input-string", _open_input_string)
    define("open-output-string", _open_output_string)
    define("get-output-string", _get_output_string)
    define("open-input-file", lambda p: _open_file(p, "r", "open-input-file", True, False))
    define("open-output-file", lambda p: _open_file(p, "w", "open-output-file", False, True))
    define("open-input-bytevector", _open_input_bytevector)
    define("open-output-bytevector", _open_output_bytevector)
    define("get-output-bytevector", _get_output_bytevector)
    define("open-binary-input-file", lambda p: _open_binary_file(p, "rb", "open-binary-input-file", True, False))
    define("open-binary-output-file", lambda p: _open_binary_file(p, "wb", "open-binary-output-file", False, True))
    define("read", lambda *rest: _read_datum(destination(rest, "current-input-port", standard_in)))
    define("read-u8", _read_u8)
    define("peek-u8", _peek_u8)
    define("u8-ready?", _u8_ready)
    define("read-bytevector", _read_bytevector)
    define("read-bytevector!", _read_bytevector_into)
    define("write-u8", _write_u8)
    define("write-bytevector", _write_bytevector)
    define("file-exists?", _file_exists)
    define("delete-file", _delete_file)
    define("file-error?", lambda e: isinstance(e, ErrorObject) and e.kind == "file")
    define("read-error?", lambda e: isinstance(e, ErrorObject) and e.kind == "read")
    define("read-char", lambda *rest: _read_char(destination(rest, "current-input-port", standard_in)))
    define("peek-char", lambda *rest: _peek_char(destination(rest, "current-input-port", standard_in)))
    define("read-line", lambda *rest: _read_line(destination(rest, "current-input-port", standard_in)))
    define("char-ready?", lambda *rest: _char_ready(destination(rest, "current-input-port", standard_in)))
    define("eof-object", lambda: EOF)
    define("eof-object?", lambda x: x is EOF)

    # -- writing: display/write/newline take an optional port --------------- #
    define("display", lambda x, *rest: _write_string_to(
        destination(rest, "current-output-port", standard_out), to_string(x, write=False)))
    define("write", lambda x, *rest: _write_string_to(
        destination(rest, "current-output-port", standard_out), to_string(x, write=True)))
    define("write-shared", lambda x, *rest: _write_string_to(
        destination(rest, "current-output-port", standard_out), to_string(x, write=True)))
    define("write-simple", lambda x, *rest: _write_string_to(
        destination(rest, "current-output-port", standard_out), to_string(x, write=True)))
    define("print", lambda *xs: _write_string_to(
        current_port("current-output-port", standard_out),
        " ".join(to_string(x, write=False) for x in xs) + "\n"))
    define("newline", lambda *rest: _write_string_to(
        destination(rest, "current-output-port", standard_out), "\n"))
    define("write-string", lambda text, *rest: _write_string_to(
        destination(rest, "current-output-port", standard_out), _expect_string(text)))
    define("write-char", lambda ch, *rest: _write_string_to(
        destination(rest, "current-output-port", standard_out), _expect_char(ch)))

    # -- the environment and the clock -------------------------------------- #
    define("exit", lambda *code: _exit(code))
    define("emergency-exit", lambda *code: _exit(code, emergency=True))
    define("command-line", lambda: list(sys.argv))
    define("get-environment-variable", lambda name: _get_env(_expect_string(name)))
    define("get-environment-variables", lambda: _environment_variables())
    define("current-second", lambda: time.time())
    define("current-jiffy", lambda: time.monotonic_ns())
    define("jiffies-per-second", lambda: 1_000_000_000)

    define("error", _error)
    define("assert", _assert)
    define("gensym", _gensym())

    # -- SRFI 19 (S10) and SRFI 160 (S11): core-backed libraries ------------- #
    # Their Python primitives are deliberately NOT bound here: they install
    # into the libraries' own private scopes on first import
    # (shslisp/library.py's `_core_backed_builder`), so the strict r7rs
    # profile sees them only through (import ...) — like every other SRFI —
    # while the default profile's pre-import binds the same objects. The
    # core floor below stays (scheme base) plus the prelude's own names.

    # The floor's own names, remembered once: this is the set the library
    # system protects from silent replacement (see shslisp/library.py). Prelude
    # aliases of these objects (`fold = foldl`, `reduce = foldl`) are *not*
    # in the set — the SRFI layer is documented to replace those.
    env.core_names = frozenset(env.vars)

    return env


# --------------------------------------------------------------------------- #
#  Number helpers                                                              #
# --------------------------------------------------------------------------- #

def _normalize_rational(value: Any) -> Any:
    """A whole ``Fraction`` is an ``int`` — the tower never holds one.

    Every exact arithmetic result passes through here (R1): ``(/ 4 2)`` is
    ``2``, not ``Fraction(2, 1)``, so ``eqv?``, hashing, and printing keep one
    spelling for one value.
    """
    if isinstance(value, Fraction) and value.denominator == 1:
        return int(value)
    return value


def _is_integer_value(x: Any) -> bool:
    """R7RS ``integer?`` is the mathematical property, not a type test (row
    12): ``3.0`` is an integer. ``exact-integer?`` is the type-strict one,
    and that distinction is why both exist.
    """
    if isinstance(x, bool):
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, float):
        return x.is_integer()
    if isinstance(x, Fraction):
        return x.denominator == 1  # unreachable post-normalization, but honest
    return False


def _real_p(x: Any) -> bool:
    """``real?`` is the mathematical property (C1 row 12): a complex with a
    zero imaginary part *is* a real — ``(real? 1.0+0.0i)`` is ``#t``. An exact
    ``Complex`` never has a zero imaginary part (the constructor collapses
    it), so only the inexact half can answer ``#t`` here."""
    if isinstance(x, bool):
        return False
    if isinstance(x, Complex):
        return False
    if isinstance(x, complex):
        return x.imag == 0
    return isinstance(x, Number)


def _rational_p(x: Any) -> bool:
    """``rational?``: the tower's real numbers are all rational (an inexact
    real is a double, a rational when finite); a complex with a nonzero
    imaginary part is not."""
    if isinstance(x, bool):
        return False
    if isinstance(x, Complex):
        return False
    if isinstance(x, complex):
        return x.imag == 0 and math.isfinite(x.real)
    return isinstance(x, Number)


def _finite_p(x: Any) -> bool:
    """``finite?``: exact numbers are neither infinite nor NaN by construction."""
    value = _expect_number(x, "finite?")
    if isinstance(value, (int, Fraction, Complex)):
        return True
    if isinstance(value, complex):
        return math.isfinite(value.real) and math.isfinite(value.imag)
    return math.isfinite(value)


def _infinite_p(x: Any) -> bool:
    """``infinite?``: a complex is infinite when either component is."""
    value = _expect_number(x, "infinite?")
    if isinstance(value, (int, Fraction, Complex)):
        return False
    if isinstance(value, complex):
        return math.isinf(value.real) or math.isinf(value.imag)
    return math.isinf(value)


def _nan_p(x: Any) -> bool:
    """``nan?``: a complex is NaN when either component is."""
    value = _expect_number(x, "nan?")
    if isinstance(value, (int, Fraction, Complex)):
        return False
    if isinstance(value, complex):
        return math.isnan(value.real) or math.isnan(value.imag)
    return math.isnan(value)


def _expect_real(x: Any, who: str) -> Any:
    """The real-only family's gate (C1 row 10): a complex with a nonzero
    imaginary part is refused loudly. R7RS's ``floor``/``min``/``<`` and the
    division family take reals, and a silent Python ``TypeError`` leaking out
    of ``math.floor`` is not an answer."""
    value = _expect_number(x, who)
    if isinstance(value, Complex) or (
        isinstance(value, complex) and value.imag != 0
    ):
        raise LispTypeError(f"{who}: expected a real number, got a complex")
    return value


def _as_real(value: Any) -> Any:
    """A complex with a zero imaginary part *is* its real part (row 12) —
    unwrap it so the orderable family works on honest floats."""
    if isinstance(value, complex) and value.imag == 0:
        return value.real
    return value


def _make_rectangular(re: Any, im: Any) -> Any:
    """The complex ``re + im·i`` (C1 rows 1–3).

    Exact components build the exact pair, and an exact zero imaginary part
    collapses to the real (row 2). An inexact component contaminates the
    whole into a Python ``complex`` (row 3), where a zero imaginary part
    stays visible — signed zero is honest.
    """
    r = _as_real(_expect_real(re, "make-rectangular"))
    i = _as_real(_expect_real(im, "make-rectangular"))
    if isinstance(r, float) or isinstance(i, float):
        return complex(r, i)
    return Complex(r, i)


def _real_part(z: Any) -> Any:
    """The real part, with its own exactness (C1 row 5)."""
    value = _expect_number(z, "real-part")
    if isinstance(value, (Complex, complex)):
        return value.real
    return value


def _imag_part(z: Any) -> Any:
    """The imaginary part, with its own exactness (C1 row 5); a real's
    imaginary part is zero, exactly as exact as the real itself."""
    value = _expect_number(z, "imag-part")
    if isinstance(value, (Complex, complex)):
        return value.imag
    if isinstance(value, float):
        return 0.0
    return 0


def _expt(a: Any, b: Any) -> Any:
    """``expt`` with the exactness rules of the design note's row 6.

    Exact base, exact negative integer exponent → the exact rational
    (``(expt 2 -1)`` is ``1/2``). A non-integral exact exponent is generally
    irrational, so the honest answer is inexact. An inexact operand gives
    IEEE double arithmetic, as everywhere else in the tower. An exact complex
    base with an exact integer exponent stays exact (C1); any other complex
    involvement answers inexact.
    """
    base = _expect_number(a, "expt")
    exponent = _expect_number(b, "expt")
    if isinstance(base, (Complex, complex)) or isinstance(exponent, (Complex, complex)):
        if isinstance(base, Complex) and isinstance(exponent, int) \
                and not isinstance(exponent, bool):
            return base ** exponent  # exact schoolbook, both signs
        left = complex(base) if isinstance(base, Complex) else base
        right = complex(exponent) if isinstance(exponent, Complex) else exponent
        return left ** right
    if isinstance(base, float) or isinstance(exponent, float):
        return base ** exponent
    if isinstance(exponent, Fraction):
        return float(base) ** float(exponent)
    if exponent >= 0:
        return _normalize_rational(base ** exponent)
    if base == 0:
        raise LispTypeError("expt: zero to a negative power is a division by zero")
    return _normalize_rational(Fraction(base) ** exponent)


def _product(xs: Iterable[Any]) -> Any:
    total = 1
    for x in xs:
        total *= _expect_number(x, "*")
    return total


def _sub(*xs: Any) -> Any:
    if not xs:
        raise LispTypeError("-: needs at least one argument")
    xs = _complex_shim(xs)
    total = _expect_number(xs[0], "-")
    if len(xs) == 1:
        return _normalize_rational(-total)
    for x in xs[1:]:
        total -= _expect_number(x, "-")
    return _normalize_rational(total)


def _div(*xs: Any) -> Any:
    """Scheme's ``/``: exactness-preserving, never silently truncating.

    Exact operands divide exactly — a rational when the division is not even
    (R1), an integer when it is, an exact complex pair by the schoolbook
    identity (C1). Any inexact operand gives IEEE double arithmetic, where a
    zero divisor has an IEEE answer (``+inf.0`` by sign, ``+nan.0`` for zero
    over zero). An *exact* zero divisor is an error, full stop: the question
    has no answer in any tower this project will build.
    """
    if not xs:
        raise LispTypeError("/: needs at least one argument")
    xs = tuple(_expect_number(x, "/") for x in xs)
    if len(xs) == 1:
        xs = (1, xs[0])
    total = xs[0]
    for x in xs[1:]:
        total = _divide(total, x)
    return total


def _divide(total: Any, x: Any) -> Any:
    """One exactness-aware division step of ``/``'s left fold."""
    if isinstance(x, (float, complex)):
        if x == 0:
            return _ieee_zero_division(total, x)
    elif x == 0:
        raise LispTypeError("/: division by zero")
    if isinstance(total, (float, complex)) or isinstance(x, (float, complex)):
        left = complex(total) if isinstance(total, Complex) else total
        right = complex(x) if isinstance(x, Complex) else x
        # Python's complex does not interop with Fraction: the rational goes
        # through its float image (the contagion already decided inexact).
        if isinstance(left, complex) and isinstance(right, Fraction):
            right = float(right)
        elif isinstance(right, complex) and isinstance(left, Fraction):
            left = float(left)
        return left / right
    if isinstance(total, Complex) or isinstance(x, Complex):
        return total / x
    return _normalize_rational(Fraction(total) / Fraction(x))


def _ieee_zero_division(total: Any, x: Any) -> Any:
    """IEEE's answer for an *inexact* zero divisor (row 1's other half).

    Pure reals keep the sign-aware infinity the tower has always answered. A
    complex zero divisor (or a complex numerator meeting a real zero) answers
    component-wise, IEEE 754 Annex G style: a zero or NaN numerator part is
    NaN, anything else is an infinity signed by the operand signs.
    """
    if isinstance(total, (Complex, complex)) or isinstance(x, complex):
        z = complex(total) if isinstance(total, Complex) else total
        if not isinstance(z, complex):
            z = complex(z)
        w = x if isinstance(x, complex) else complex(x)

        def component(numerator: float, divisor_part: float) -> float:
            if numerator == 0 or math.isnan(numerator):
                return float("nan")
            sign = math.copysign(1.0, numerator) * math.copysign(1.0, divisor_part)
            return math.copysign(float("inf"), sign)

        return complex(component(z.real, w.real), component(z.imag, w.imag))
    if total == 0 or (isinstance(total, float) and math.isnan(total)):
        return float("nan")
    sign = math.copysign(1.0, total) * math.copysign(1.0, x)
    return math.copysign(float("inf"), sign)


def _complex_shim(values: tuple) -> tuple:
    """Python's ``complex`` does not interoperate with ``Fraction``: where an
    inexact complex meets an exact rational, the rational goes through its
    float image — the contagion has already decided the answer is inexact."""
    if not any(isinstance(v, complex) for v in values):
        return values
    return tuple(float(v) if isinstance(v, Fraction) else v for v in values)


def _chain(xs: tuple, op: Callable[[Any, Any], bool], ordered: bool = False) -> bool:
    if ordered:
        # The ordering family takes reals only (C1 row 10), and a complex
        # with a zero imaginary part is its real part (row 12).
        xs = tuple(_as_real(_expect_real(x, "comparison")) for x in xs)
    else:
        xs = tuple(_as_real(_expect_number(x, "comparison")) for x in xs)
    return all(op(a, b) for a, b in zip(xs, xs[1:]))


def _min(*xs: Any) -> Any:
    if len(xs) == 1 and isinstance(xs[0], list):
        xs = tuple(xs[0])
    values = tuple(_as_real(_expect_real(x, "min")) for x in xs)
    result = min(values)
    # Row 10: any inexact argument contaminates the result.
    if any(isinstance(v, float) for v in values):
        return float(result)
    return result


def _max(*xs: Any) -> Any:
    if len(xs) == 1 and isinstance(xs[0], list):
        xs = tuple(xs[0])
    values = tuple(_as_real(_expect_real(x, "max")) for x in xs)
    result = max(values)
    # Row 10: any inexact argument contaminates the result.
    if any(isinstance(v, float) for v in values):
        return float(result)
    return result


def _modulo(a: int, b: int) -> int:
    a = _expect_real(a, "modulo")
    b = _expect_real(b, "modulo")
    if b == 0:
        raise LispTypeError("modulo: division by zero")
    return a % b


def _quotient(a: int, b: int) -> int:
    """Integer division truncating toward zero (Scheme's ``quotient``).

    Python's ``/`` would route even exact integers through a float, losing
    precision past 2**53; ``//`` floors instead of truncating. Do it with
    integer arithmetic so bignums stay exact and ``(quotient -7 2)`` is ``-3``.
    Rationals truncate the same way; inexactness is preserved (row 9).
    """
    a = _expect_real(a, "quotient")
    b = _expect_real(b, "quotient")
    if b == 0:
        raise LispTypeError("quotient: division by zero")
    if isinstance(a, float) or isinstance(b, float):
        return float(int(a / b))
    q = abs(a) // abs(b)
    return _normalize_rational(q if (a < 0) == (b < 0) else -q)


def _remainder(a: int, b: int) -> int:
    """The remainder whose sign follows the dividend (Scheme's ``remainder``)."""
    a = _expect_real(a, "remainder")
    b = _expect_real(b, "remainder")
    if b == 0:
        raise LispTypeError("remainder: division by zero")
    if isinstance(a, float) or isinstance(b, float):
        return a - b * int(a / b)
    return _normalize_rational(a - b * _quotient(a, b))


def _math1(name: str, fn: Callable[[float], float], cfn: Any, x: Any) -> Any:
    """Apply a ``math`` function — or its ``cmath`` twin for complex input.

    A real argument uses the real function; a domain error there (``asin``
    of 2) falls back to the complex answer now that the tower has one (C2),
    the way R7RS's complex-supporting implementations behave. An OverflowError
    is still a Lisp error: no double can hold it.
    """
    value = _expect_number(x, name)
    if isinstance(value, (Complex, complex)):
        z = complex(value) if isinstance(value, Complex) else value
        try:
            return cfn(z)
        except ValueError as error:
            raise LispTypeError(f"{name}: {error}") from None
    try:
        return float(fn(value))
    except ValueError:
        # The real function refused the domain; the complex one may answer.
        try:
            return cfn(complex(value))
        except ValueError as error:
            raise LispTypeError(f"{name}: {error}") from None
    except OverflowError as error:
        raise LispTypeError(f"{name}: {error}") from None


def _log(x: Any, base: Any = None) -> Any:
    """``(log x)`` natural, ``(log x base)`` in that base.

    A negative or complex argument answers the complex logarithm (C2 row 8):
    ``(log -1)`` is ``+iπ``, inexact — π is irrational. ``(log 0)`` is an
    error in both worlds, and stays one.
    """
    value = _expect_number(x, "log")
    negative = isinstance(value, (int, float, Fraction)) and value < 0
    if isinstance(value, (Complex, complex)) or negative:
        z = complex(value) if isinstance(value, Complex) else value
        try:
            return cmath.log(z)
        except ValueError as error:
            raise LispTypeError(f"log: {error}") from None
    try:
        if base is None:
            return float(math.log(value))
        radix = _expect_real(base, "log")
        return float(math.log(value) / math.log(radix))
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        raise LispTypeError(f"log: {error}") from None


def _atan(y: Any, x: Any = None) -> Any:
    """``(atan y)`` or the two-argument ``(atan y x)``.

    The one-argument form is complex-aware (C2); the two-argument form is
    IEEE ``atan2`` over the reals — an angle has one pair of components.
    """
    if x is None:
        return _math1("atan", math.atan, cmath.atan, y)
    try:
        return float(math.atan2(_expect_real(y, "atan"), _expect_real(x, "atan")))
    except (ValueError, OverflowError) as error:
        raise LispTypeError(f"atan: {error}") from None


def _sqrt(x: Any) -> Any:
    """``sqrt``: an exact value with an exact rational root stays exact.

    An exact integer's perfect square is its own root; a rational's root is
    exact exactly when numerator and denominator both are perfect squares
    (row 7 — ``(sqrt 1/4)`` is ``1/2``). A negative real's root is complex
    (C2 row 8): exact when the magnitude's root is a perfect rational square
    — ``(sqrt -4)`` is the exact ``2i`` — and honestly inexact otherwise
    (``(sqrt -2)``). A complex argument answers the principal root through
    ``cmath``.
    """
    value = _expect_number(x, "sqrt")
    if isinstance(value, (Complex, complex)):
        z = complex(value) if isinstance(value, Complex) else value
        return cmath.sqrt(z)
    if value < 0:
        magnitude = -value
        if isinstance(magnitude, int):
            root = math.isqrt(magnitude)
            if root * root == magnitude:
                return Complex(0, root)
        elif isinstance(magnitude, Fraction):
            root_n = math.isqrt(magnitude.numerator)
            root_d = math.isqrt(magnitude.denominator)
            if root_n * root_n == magnitude.numerator \
                    and root_d * root_d == magnitude.denominator:
                return Complex(0, _normalize_rational(Fraction(root_n, root_d)))
        return cmath.sqrt(complex(value))
    if isinstance(value, int):
        root = math.isqrt(value)
        if root * root == value:
            return root
    elif isinstance(value, Fraction):
        root_n = math.isqrt(value.numerator)
        root_d = math.isqrt(value.denominator)
        if root_n * root_n == value.numerator and root_d * root_d == value.denominator:
            return _normalize_rational(Fraction(root_n, root_d))
    return math.sqrt(value)


def _angle_prim(z: Any) -> Any:
    """``angle``: the phase in radians (C2 row 7).

    A positive real answers exact ``0``; a negative real answers ``π``,
    inexact — π is not rational. An inexact argument goes through
    ``cmath.phase``, which honours signed zero the way IEEE ``atan2`` does
    (``(angle -0.0)`` is ``π``, not ``0.0``). An exact complex pair answers
    through ``atan2`` over its parts, also inexact.
    """
    value = _expect_number(z, "angle")
    if isinstance(value, Complex):
        return _exact_angle(value.real, value.imag)
    if isinstance(value, complex):
        return cmath.phase(value)
    if isinstance(value, float):
        return cmath.phase(complex(value, 0.0))
    if value >= 0:
        return 0
    return math.pi


def _exact_angle(a: Any, b: Any) -> float:
    """``atan2(b, a)`` for exact parts, safe for bignums: the angle is
    scale-invariant, so both parts shrink by the larger magnitude first."""
    ra, rb = Fraction(a), Fraction(b)
    scale = max(abs(ra), abs(rb))
    if scale == 0:
        return 0.0
    return math.atan2(float(rb / scale), float(ra / scale))


def _make_polar(magnitude: Any, angle: Any) -> Any:
    """The complex ``magnitude·e^(i·angle)`` (C2 row 4).

    Exact parts with a zero angle answer the exact magnitude — ``(make-polar
    2 0)`` is ``2``. A nonzero exact angle has no exact cosine, so the honest
    answer is inexact. Any inexact part contaminates through ``cmath.rect``.
    """
    m = _expect_real(magnitude, "make-polar")
    a = _expect_real(angle, "make-polar")
    if isinstance(m, float) or isinstance(a, float):
        return cmath.rect(m, a)
    if a == 0:
        return _normalize_rational(m)
    return cmath.rect(float(m), float(a))


def _floor(x: Any) -> Any:
    value = _expect_real(x, "floor")
    return float(math.floor(value)) if isinstance(value, float) else math.floor(value)


def _ceiling(x: Any) -> Any:
    value = _expect_real(x, "ceiling")
    return float(math.ceil(value)) if isinstance(value, float) else math.ceil(value)


def _truncate(x: Any) -> Any:
    value = _expect_real(x, "truncate")
    return float(math.trunc(value)) if isinstance(value, float) else math.trunc(value)


def _round(x: Any) -> Any:
    value = _expect_real(x, "round")
    # Python's round() is ties-to-even, which is what R7RS asks for.
    return float(round(value)) if isinstance(value, float) else round(value)


def _floor_quotient(a: int, b: int) -> int:
    """Integer division rounding toward negative infinity (R7RS ``floor-quotient``).

    Rationals floor the exact quotient; integral inexact integers are
    accepted and the result stays inexact.
    """
    a = _expect_real(a, "floor-quotient")
    b = _expect_real(b, "floor-quotient")
    if b == 0:
        raise LispTypeError("floor-quotient: division by zero")
    if isinstance(a, float) or isinstance(b, float):
        return float(math.floor(a / b))
    return _normalize_rational(Fraction(a) // Fraction(b))


def _floor_remainder(a: int, b: int) -> int:
    """The remainder whose sign follows the divisor (R7RS ``floor-remainder``)."""
    a = _expect_real(a, "floor-remainder")
    b = _expect_real(b, "floor-remainder")
    if b == 0:
        raise LispTypeError("floor-remainder: division by zero")
    if isinstance(a, float) or isinstance(b, float):
        return a % b
    return _normalize_rational(Fraction(a) % Fraction(b))


def _exact(x: Any) -> Any:
    """``exact``: an exact value passes through; an inexact value converts to
    the exact rational *numerically equal* to it (row 4 of the design note).

    The conversion is honest about the double: ``(exact 0.1)`` is the exact
    binary value ``3602879701896397/36028797018963968``, not ``1/10`` — write
    ``#e0.1`` when the decimal itself is what you mean. An infinity or a NaN
    has no exact equal, so it raises.
    """
    value = _expect_number(x, "exact")
    if isinstance(value, (int, Fraction, Complex)):
        return value
    if isinstance(value, complex):
        if not (math.isfinite(value.real) and math.isfinite(value.imag)):
            raise LispTypeError("exact: an infinity or a NaN has no exact equal")
        # The exact image of the double pair; a zero imaginary part collapses
        # to the real (C1 row 2 — ``(exact 1.0+0.0i)`` is ``1``).
        return Complex(Fraction(value.real), Fraction(value.imag))
    if not math.isfinite(value):
        raise LispTypeError("exact: an infinity or a NaN has no exact equal")
    return _normalize_rational(Fraction(value))


def _inexact(x: Any) -> float:
    value = _expect_number(x, "inexact")
    if isinstance(value, Complex):
        return complex(value)
    if isinstance(value, complex):
        return value
    return float(value)


def _exact_integer_sqrt(n: Any) -> Values:
    """``(values s r)`` with ``s*s <= n < (s+1)*(s+1)`` and ``r = n - s*s``."""
    value = _expect_int(n, "exact-integer-sqrt")
    if value < 0:
        raise LispTypeError("exact-integer-sqrt: expected a non-negative integer")
    root = math.isqrt(value)
    return Values((root, value - root * root))


def _numerator(x: Any) -> Any:
    """The numerator of *x*; exact values keep exactness, floats stay inexact."""
    value = _expect_real(x, "numerator")
    if isinstance(value, Fraction):
        return value.numerator
    if isinstance(value, int):
        return value
    if not math.isfinite(value):
        raise LispTypeError("numerator: expected a finite number")
    top, _ = value.as_integer_ratio()
    return float(top)


def _denominator(x: Any) -> Any:
    """The denominator of *x*; exact integers have denominator ``1``."""
    value = _expect_real(x, "denominator")
    if isinstance(value, Fraction):
        return value.denominator
    if isinstance(value, int):
        return 1
    if not math.isfinite(value):
        raise LispTypeError("denominator: expected a finite number")
    _, bottom = value.as_integer_ratio()
    return float(bottom)


def _simplest(lo: Fraction, hi: Fraction) -> Fraction:
    """The simplest rational in ``[lo, hi]`` — fewest denominator digits.

    The classic continued-fraction algorithm: mirror negatives, answer 0 or 1
    when the interval contains them, otherwise peel off the integer part and
    recurse on the reciprocals of the fractional remainders. Terminates
    because each recursion strictly shrinks the interval's distance from the
    nearest integer.
    """
    if lo > hi:
        lo, hi = hi, lo
    if lo == hi:
        return lo
    if lo < 0:
        if hi < 0:
            return -_simplest(-hi, -lo)
        return Fraction(0)
    if lo == 0:
        return Fraction(0)
    if lo < 1 <= hi:
        return Fraction(1)
    if hi < 1:
        # 0 < lo < hi < 1: reciprocals flip the interval past 1.
        return 1 / _simplest(1 / hi, 1 / lo)
    # 1 <= lo < hi: peel the integer part.
    n = lo.numerator // lo.denominator
    if n + 1 <= hi:
        return Fraction(n + 1)
    return n + 1 / _simplest(1 / (hi - n), 1 / (lo - n))


def _rationalize(x: Any, tolerance: Any) -> Any:
    """The simplest rational within *tolerance* of *x* (R7RS).

    Exact operands answer an exact rational — ``(rationalize 7/2 1/5)`` is
    ``7/2``. Any inexact operand makes the result inexact (row 5): the work
    happens exactly, then converts. An infinity or a NaN has no nearest
    rational, so it raises.
    """
    xv = _expect_real(x, "rationalize")
    tv = _expect_real(tolerance, "rationalize")
    inexact = isinstance(xv, float) or isinstance(tv, float)
    if inexact and (not math.isfinite(xv) or not math.isfinite(tv)):
        raise LispTypeError("rationalize: expected finite numbers")
    exact_x, exact_y = Fraction(xv), Fraction(tv)
    if exact_y < 0:
        exact_y = -exact_y
    if exact_y == 0:
        result = exact_x
    else:
        result = _simplest(exact_x - exact_y, exact_x + exact_y)
    return float(result) if inexact else _normalize_rational(result)


# --------------------------------------------------------------------------- #
#  The rest of the numeric tower, and the equality it needs                     #
# --------------------------------------------------------------------------- #
#
# The tower is *two* types: exact integers (Python ``int``, unbounded) and
# inexact reals (``float``). Saying so out loud — ``exact?``/``inexact?`` — is
# what lets a program branch on exactness instead of guessing, and it is the
# honest scope of "one numeric tower".

def _expect_number(x: Any, who: str) -> Any:
    if isinstance(x, Number) and not isinstance(x, bool):
        return x
    raise LispTypeError(f"{who}: expected a number, got {type(x).__name__}")


def _expect_int(x: Any, who: str) -> int:
    if isinstance(x, int) and not isinstance(x, bool):
        return x
    raise LispTypeError(f"{who}: expected an integer, got {type(x).__name__}")


def _rational_gcd_lcm(values: tuple, who: str, lcm: bool) -> Any:
    """The shared engine for ``gcd``/``lcm`` over the whole exact tower.

    For rationals the identities are ``gcd(a/b, c/d) = gcd(a·d, c·b)/(b·d)``
    and ``lcm(a/b, c/d) = lcm(a·d, c·b)/(b·d)`` — in numerator/denominator
    terms, gcd pairs numerators with the *lcm* of denominators and vice versa.
    Integral inexact integers are accepted (R7RS's whole-value rule, row 8);
    any inexact argument makes the result inexact.
    """
    inexact = any(isinstance(v, float) for v in values)
    rationals = []
    for value in values:
        n = _expect_real(value, who)
        if isinstance(n, float):
            if not n.is_integer():
                raise LispTypeError(
                    f"{who}: expected an integer, got a non-integral float"
                )
            rationals.append(Fraction(int(n)))
        else:
            rationals.append(Fraction(n))
    if lcm:
        top, bottom = 1, 1
        for r in rationals:
            top = (
                0
                if top == 0 or r.numerator == 0
                else abs(top * r.numerator) // math.gcd(top, r.numerator)
            )
            bottom = math.gcd(bottom, r.denominator)
    else:
        top, bottom = 0, 1
        for r in rationals:
            top = math.gcd(top, r.numerator)
            bottom = bottom * r.denominator // math.gcd(bottom, r.denominator)
    result = _normalize_rational(Fraction(top, bottom))
    return float(result) if inexact else result


def _gcd(values: tuple) -> Any:
    return _rational_gcd_lcm(values, "gcd", lcm=False)


def _lcm(values: tuple) -> Any:
    return _rational_gcd_lcm(values, "lcm", lcm=True)


def _number_to_string(n: Any, radix: int = 10) -> str:
    _expect_number(n, "number->string")
    if radix == 10:
        return to_string(n)  # keep the printer's own float formatting
    if radix not in (2, 8, 16):
        raise LispTypeError(
            f"number->string: radix must be 2, 8, 10, or 16, got {radix}"
        )
    if not isinstance(n, int):
        raise LispTypeError("number->string: a radix other than 10 needs an integer")
    sign = "-" if n < 0 else ""
    return sign + format(abs(n), {2: "b", 8: "o", 16: "x"}[radix])


def _eqv(a: Any, b: Any) -> bool:
    """Scheme's ``eqv?``, as far as this tower goes.

    Numbers compare by value *and* exactness (``(eqv? 1 1.0)`` is ``#f``);
    characters and symbols are interned, so identity is exact; everything else
    falls back to ``eq?``.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, Number) and isinstance(b, Number):
        return type(a) is type(b) and a == b
    return _eq(a, b)


# --------------------------------------------------------------------------- #
#  List helpers                                                                #
# --------------------------------------------------------------------------- #

def _expect_list(xs: Any, who: str) -> list:
    try:
        return list_to_python(xs)
    except LispError:
        raise LispTypeError(f"{who}: expected a list") from None


def _cons(x: Any, xs: Any) -> Any:
    if is_nil(xs):
        return [x]
    if isinstance(xs, list):
        return [x, *xs]
    return Pair(x, xs)


def _car(xs: Any) -> Any:
    if isinstance(xs, list) and xs:
        return xs[0]
    if isinstance(xs, Pair):
        return xs.car
    raise LispTypeError("car: expected a non-empty list")


def _cdr(xs: Any) -> Any:
    if isinstance(xs, list) and xs:
        return make_list(xs[1:])
    if isinstance(xs, Pair):
        return xs.cdr
    raise LispTypeError("cdr: expected a non-empty list")


def _length(xs: Any) -> int:
    # A proper list *is* a Python list, so ask it directly: copying it first
    # (as ``list_to_python`` does) would make every `length` allocate.
    if is_nil(xs):
        return 0
    if isinstance(xs, list):
        return len(xs)
    return len(list_to_python(xs))


def _append(*lists: Any) -> Any:
    if not lists:
        return NIL
    out: list = []
    for xs in lists[:-1]:
        out.extend(_expect_list(xs, "append"))
    last = lists[-1]
    if is_nil(last):
        return make_list(out)
    if isinstance(last, list):
        return make_list(out + last)
    if isinstance(last, Pair):
        cells: list = []
        node: Any = last
        while isinstance(node, Pair):
            cells.append(node.car)
            node = node.cdr
        return from_cells(out + cells, node)
    return from_cells(out, last)  # the last argument may be any object


def _list_ref(xs: Any, index: int) -> Any:
    # Index a proper list directly — it *is* a Python list, and copying it to
    # read one element would make an indexed walk quadratic.
    if index < 0:
        raise LispTypeError(f"list-ref: index {index} out of range (must be >= 0)")
    if isinstance(xs, list):
        if index < len(xs):
            return xs[index]
        raise LispTypeError(f"list-ref: index {index} out of range")
    seq = list_to_python(xs)
    if index >= len(seq):
        raise LispTypeError(f"list-ref: index {index} out of range")
    return seq[index]


def _list_tail(xs: Any, index: int) -> Any:
    if index < 0:
        raise LispTypeError(f"list-tail: index {index} out of range (must be >= 0)")
    if isinstance(xs, Pair):
        node: Any = xs
        for _ in range(index):
            if not isinstance(node, Pair):
                raise LispTypeError(f"list-tail: index {index} out of range")
            node = node.cdr
        return node
    seq = list_to_python(xs)
    if index > len(seq):
        raise LispTypeError(f"list-tail: index {index} out of range")
    return make_list(seq[index:])


def _take(xs: Any, count: int) -> Any:
    """The first *count* elements, as a fresh proper list.

    A primitive, not the prelude's recursive ``cons`` walk: a proper list is a
    Python list, so prepending one element at a time copies the tail and makes
    ``take`` quadratic (50k elements cost ~0.65 s). Slicing is one pass.
    """
    if count <= 0 or is_nil(xs):
        return NIL
    return make_list(_expect_list(xs, "take")[:count])


def _drop(xs: Any, count: int) -> Any:
    """Everything after the first *count* elements (the list itself when 0)."""
    if count <= 0:
        return xs
    return make_list(_expect_list(xs, "drop")[count:])


def _make_list(count: int, fill: Any = False) -> Any:
    return make_list([fill] * max(0, count))


def _foldl(f: Any, acc: Any, xs: Any) -> Any:
    for x in list_to_python(xs):
        acc = apply_procedure(f, [x, acc])
    return acc


def _foldr(f: Any, acc: Any, xs: Any) -> Any:
    for x in reversed(list_to_python(xs)):
        acc = apply_procedure(f, [x, acc])
    return acc


def _columns(lists: tuple, who: str) -> list:
    """The argument lists of a multi-list walk, required to be equal in length.

    R7RS makes differing lengths an error rather than truncating them: a `map`
    that silently stops is a bug you meet much later than one that says so.
    """
    if not lists:
        raise LispTypeError(f"{who}: expected at least one list")
    cols = [_expect_list(xs, who) for xs in lists]
    if len(cols) > 1:
        lengths = sorted({len(col) for col in cols})
        if len(lengths) > 1:
            raise LispTypeError(
                f"{who}: lists must be the same length, got "
                + ", ".join(str(n) for n in lengths)
            )
    return cols


def _map(f: Any, *lists: Any) -> Any:
    """``(map f xs ...)`` — R7RS: walk one list, or several in step."""
    cols = _columns(lists, "map")
    return make_list(apply_procedure(f, list(row)) for row in zip(*cols))


def _for_each(f: Any, *lists: Any) -> Any:
    cols = _columns(lists, "for-each")
    for row in zip(*cols):
        apply_procedure(f, list(row))
    return NIL


def _range(*args: Any) -> Any:
    if len(args) == 1:
        start, stop, step = 0, args[0], 1
    elif len(args) in (2, 3):
        start, stop = args[0], args[1]
        step = args[2] if len(args) == 3 else 1
    else:
        raise LispTypeError("range: expected 1 to 3 arguments")
    return make_list(range(start, stop, step))


def _member(x: Any, xs: Any) -> Any:
    for item in list_to_python(xs):
        if equal(x, item):
            return True
    return False


def _member_pair(x: Any, xs: Any, compare: Any = None) -> Any:
    """Scheme's ``member``: the tail beginning at the first match, or ``#f``.

    R7RS and SRFI 1 both add an optional comparator; the two-argument form is
    unchanged (``equal?``). This is the ONE binding both ``(scheme base)`` and
    ``(srfi 1)`` re-export, so the combined import never collides.
    """
    if compare is None:
        eqf: Callable[[Any, Any], bool] = equal
    else:
        eqf = lambda a, b: is_true(apply_procedure(compare, [a, b]))
    cells = list_to_python(xs)
    for index, item in enumerate(cells):
        if eqf(x, item):
            return make_list(cells[index:])
    return False


def _memq(x: Any, xs: Any, eqf: Callable[[Any, Any], bool]) -> Any:
    seq = list_to_python(xs)
    for index, item in enumerate(seq):
        if eqf(x, item):
            return make_list(seq[index:])
    return False


def _assoc(key: Any, alist: Any, compare: Any = None) -> Any:
    """Scheme's ``assoc``: the first pair whose key matches, or ``#f``.

    The optional comparator is the same one-extended-binding decision as
    ``member`` (R7RS and SRFI 1 agree).
    """
    if compare is None:
        eqf: Callable[[Any, Any], bool] = equal
    else:
        eqf = lambda a, b: is_true(apply_procedure(compare, [a, b]))
    for entry in list_to_python(alist):
        if is_pair(entry) and eqf(key, _car(entry)):
            return entry
    return False


def _assoc_with(key: Any, alist: Any, eqf: Callable[[Any, Any], bool]) -> Any:
    for entry in list_to_python(alist):
        if is_pair(entry) and eqf(key, _car(entry)):
            return entry
    return False


def _set_car(pair: Any, value: Any) -> Any:
    """``(set-car! pair value)`` — mutate the first cell of a pair or list."""
    if isinstance(pair, Pair):
        pair.car = value
        return NIL
    if isinstance(pair, list) and pair:
        pair[0] = value
        return NIL
    raise LispTypeError(
        f"set-car!: expected a pair, got {type(pair).__name__}"
    )


def _set_cdr(pair: Any, value: Any) -> Any:
    """``(set-cdr! pair value)`` — mutate a Pair cell's tail.

    A proper list is a Python ``list``, whose tail *type* cannot change in
    place, so ``set-cdr!`` is supported on :class:`~shslisp.types.Pair` cells
    only; a proper list's tail type change is a documented limitation
    (``docs/srfi.md``).
    """
    if isinstance(pair, Pair):
        pair.cdr = value
        return NIL
    raise LispTypeError(
        f"set-cdr!: expected a Pair cell (a proper list's tail type cannot "
        f"change in place), got {type(pair).__name__}"
    )


def _sort(lst: Any, less: Any) -> Any:
    """A stable sort of *lst* by the ``less`` predicate."""
    import functools

    def compare(a: Any, b: Any) -> int:
        if is_true(apply_procedure(less, [a, b])):
            return -1
        if is_true(apply_procedure(less, [b, a])):
            return 1
        return 0

    items = sorted(list_to_python(lst), key=functools.cmp_to_key(compare))
    return make_list(items)


# --------------------------------------------------------------------------- #
#  Equality, application, strings, and host hooks                              #
# --------------------------------------------------------------------------- #

def _eq(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float, str, bool)) or isinstance(
        b, (int, float, str, bool)
    ):
        return equal(a, b)
    if isinstance(a, Char) or isinstance(b, Char):
        return isinstance(a, Char) and isinstance(b, Char) and a.value == b.value
    return a is b


# --------------------------------------------------------------------------- #
#  Characters, strings, vectors, and hash tables                               #
# --------------------------------------------------------------------------- #

def _char(value: str) -> Char:
    from .types import intern_char

    return intern_char(value)


def _expect_char(x: Any) -> str:
    if isinstance(x, Char):
        return x.value
    raise LispTypeError(f"expected a character, got {type(x).__name__}")


def _char_chain(chars: tuple, op: Callable[[str, str], bool]) -> bool:
    values = [_expect_char(c) for c in chars]
    return all(op(a, b) for a, b in zip(values, values[1:]))


def _fold_char(ch: str) -> str:
    """A one-character simple-ish case fold.

    ``str.casefold`` is full Unicode folding and can expand one character into
    several (``ß`` -> ``ss``); a Scheme character must stay one character, so
    an expansion falls back to ``lower`` and then to the character itself.
    """
    folded = ch.casefold()
    if len(folded) == 1:
        return folded
    lowered = ch.lower()
    return lowered if len(lowered) == 1 else ch


def _char_ci_chain(chars: tuple, op: Callable[[str, str], bool]) -> bool:
    values = [_fold_char(_expect_char(c)) for c in chars]
    return all(op(a, b) for a, b in zip(values, values[1:]))


def _digit_value(c: Any) -> Any:
    """The decimal value of a digit character, or ``#f`` (R7RS ``digit-value``)."""
    value = _expect_char(c)
    try:
        return int(unicodedata.digit(value))
    except (TypeError, ValueError):
        return False


def _symbol_chain(symbols: tuple) -> bool:
    values = []
    for value in symbols:
        if not isinstance(value, Symbol):
            raise LispTypeError(f"symbol=?: expected a symbol, got {type(value).__name__}")
        values.append(str(value))
    return all(a == b for a, b in zip(values, values[1:]))


def _string_ci_chain(strings: tuple, op: Callable[[str, str], bool]) -> bool:
    values = [_expect_string(s).casefold() for s in strings]
    return all(op(a, b) for a, b in zip(values, values[1:]))


def _make_cxr(name: str) -> Callable[[Any], Any]:
    """Build ``caddr``-style accessors by composing ``car``/``cdr``.

    The letters between the outer ``c`` and ``r`` apply right to left:
    ``caddr`` is ``(car (cdr (cdr x)))``.
    """

    def access(value: Any) -> Any:
        node = value
        for letter in reversed(name[1:-1]):
            node = _car(node) if letter == "a" else _cdr(node)
        return node

    access.__name__ = name
    return access


def _string_ref(s: Any, index: int) -> Any:
    text = _expect_string(s)
    if index < 0 or index >= len(text):
        raise LispTypeError(f"string-ref: index {index} out of range")
    return _char(text[index])


def _make_string(count: int, fill: Any = None) -> MutableString:
    ch = " " if fill is None else _expect_char(fill)
    return MutableString(ch * max(0, count))


def _string_set(s: Any, index: int, ch: Any) -> Any:
    text = _expect_mutable_string(s, "string-set!")
    if not (isinstance(index, int) and not isinstance(index, bool) and 0 <= index < len(text.chars)):
        raise LispTypeError(f"string-set!: index {index} out of range")
    text.chars[index] = _expect_char(ch)
    return NIL


def _string_fill(s: Any, ch: Any, start: int = 0, end: Optional[int] = None) -> Any:
    text = _expect_mutable_string(s, "string-fill!")
    stop = len(text.chars) if end is None else end
    if not 0 <= start <= stop <= len(text.chars):
        raise LispTypeError(f"string-fill!: range {start}..{stop} out of range")
    text.chars[start:stop] = [_expect_char(ch)] * (stop - start)
    return NIL


def _string_copy_into(
    target: Any,
    at: int,
    source: Any,
    start: int = 0,
    end: Optional[int] = None,
) -> Any:
    to = _expect_mutable_string(target, "string-copy!")
    from_ = _expect_string(source)
    stop = len(from_) if end is None else end
    if not 0 <= start <= stop <= len(from_):
        raise LispTypeError(
            f"string-copy!: source range {start}..{stop} is outside 0..{len(from_)}"
        )
    chunk = from_[start:stop]  # snapshot first: overlap is legal
    if at < 0 or at + len(chunk) > len(to.chars):
        raise LispTypeError(f"string-copy!: destination index {at} out of range")
    to.chars[at : at + len(chunk)] = list(chunk)
    return NIL


def _list_to_string(chars: Any) -> str:
    out = []
    for c in list_to_python(chars):
        out.append(_expect_char(c))
    return "".join(out)


def _string_split(s: Any, sep: Any = None) -> Any:
    text = _expect_string(s)
    parts = text.split() if sep is None else text.split(_expect_string(sep))
    return make_list(parts)


def _string_join(parts: Any, sep: Any = "") -> str:
    return _expect_string(sep).join(_expect_string(p) for p in list_to_python(parts))


def _expect_vector(x: Any) -> Vector:
    if isinstance(x, Vector):
        return x
    raise LispTypeError(f"expected a vector, got {type(x).__name__}")


def _make_vector(count: int, fill: Any = False) -> Vector:
    return Vector([fill] * max(0, count))


def _vector_ref(v: Any, index: int) -> Any:
    vec = _expect_vector(v)
    if index < 0 or index >= len(vec.items):
        raise LispTypeError(f"vector-ref: index {index} out of range")
    return vec.items[index]


def _vector_set(v: Any, index: int, value: Any) -> Any:
    vec = _expect_vector(v)
    if index < 0 or index >= len(vec.items):
        raise LispTypeError(f"vector-set!: index {index} out of range")
    vec.items[index] = value
    return NIL


def _vector_fill(v: Any, value: Any) -> Any:
    vec = _expect_vector(v)
    for i in range(len(vec.items)):
        vec.items[i] = value
    return NIL


def _vector_copy(v: Any, start: int = 0, end: Optional[int] = None) -> Vector:
    vec = _expect_vector(v)
    return Vector(vec.items[start:] if end is None else vec.items[start:end])


def _vector_copy_into(
    target: Any,
    at: int,
    source: Any,
    start: int = 0,
    end: Optional[int] = None,
) -> Any:
    """``(vector-copy! to at from [start [end]])``; overlap is safe."""
    to = _expect_vector(target)
    from_ = _expect_vector(source)
    if end is None:
        end = len(from_)
    if not (0 <= start <= end <= len(from_)):
        raise LispTypeError(
            f"vector-copy!: source range {start}..{end} is outside 0..{len(from_)}"
        )
    chunk = list(from_.items[start:end])  # snapshot first: overlap is legal
    if at < 0 or at + len(chunk) > len(to):
        raise LispTypeError(f"vector-copy!: destination index {at} out of range")
    to.items[at : at + len(chunk)] = chunk
    return NIL


def _vector_append(*vectors: Any) -> Vector:
    out: list = []
    for v in vectors:
        out.extend(_expect_vector(v).items)
    return Vector(out)


def _vectors_in_step(vectors: tuple, who: str) -> list:
    """The columns of a multi-vector walk, required to be equal in length.

    The list walk (``_columns``) refuses differing lengths; vectors must agree
    with it rather than silently truncating to the shortest.
    """
    if not vectors:
        raise LispTypeError(f"{who}: expected at least one vector")
    cols = [_expect_vector(v).items for v in vectors]
    if len(cols) > 1:
        lengths = sorted({len(col) for col in cols})
        if len(lengths) > 1:
            raise LispTypeError(
                f"{who}: vectors must be the same length, got "
                + ", ".join(str(n) for n in lengths)
            )
    return cols


def _vector_map(f: Any, *vectors: Any) -> Vector:
    cols = _vectors_in_step(vectors, "vector-map")
    return Vector(
        apply_procedure(f, list(row)) for row in zip(*cols)
    )


def _vector_for_each(f: Any, *vectors: Any) -> Any:
    cols = _vectors_in_step(vectors, "vector-for-each")
    for row in zip(*cols):
        apply_procedure(f, list(row))
    return NIL


def _expect_bytevector(x: Any, who: str) -> ByteVector:
    if isinstance(x, ByteVector):
        return x
    raise LispTypeError(f"{who}: expected a bytevector, got {type(x).__name__}")


def _expect_u8(value: Any, who: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= 255
    ):
        raise LispTypeError(
            f"{who}: expected an exact integer in 0..255, "
            f"got {to_string(value, write=True)}"
        )
    return value


def _bytevector_range(bv: ByteVector, start: Any, end: Any, who: str) -> tuple[int, int]:
    if start is None:
        start = 0
    if end is None:
        end = len(bv)
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or not 0 <= start <= end <= len(bv)
    ):
        raise LispTypeError(f"{who}: bad range {start}..{end} for length {len(bv)}")
    return start, end


def _make_bytevector(count: int, fill: int = 0) -> ByteVector:
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise LispTypeError("make-bytevector: expected a non-negative integer length")
    return ByteVector([_expect_u8(fill, "make-bytevector")] * count)


def _bytevector(*bytes_: Any) -> ByteVector:
    return ByteVector([_expect_u8(byte, "bytevector") for byte in bytes_])


def _bytevector_u8_ref(bv: Any, index: int) -> int:
    value = _expect_bytevector(bv, "bytevector-u8-ref")
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or not 0 <= index < len(value)
    ):
        raise LispTypeError(f"bytevector-u8-ref: index {index} out of range")
    return value.data[index]


def _bytevector_u8_set(bv: Any, index: int, byte: Any) -> Any:
    value = _expect_bytevector(bv, "bytevector-u8-set!")
    if (
        isinstance(index, bool)
        or not isinstance(index, int)
        or not 0 <= index < len(value)
    ):
        raise LispTypeError(f"bytevector-u8-set!: index {index} out of range")
    value.data[index] = _expect_u8(byte, "bytevector-u8-set!")
    return NIL


def _bytevector_copy(bv: Any, start: int = 0, end: Optional[int] = None) -> ByteVector:
    value = _expect_bytevector(bv, "bytevector-copy")
    first, last = _bytevector_range(value, start, end, "bytevector-copy")
    return ByteVector(value.data[first:last])


def _bytevector_copy_into(
    target: Any,
    at: int,
    source: Any,
    start: int = 0,
    end: Optional[int] = None,
) -> Any:
    to = _expect_bytevector(target, "bytevector-copy!")
    from_ = _expect_bytevector(source, "bytevector-copy!")
    first, last = _bytevector_range(from_, start, end, "bytevector-copy!")
    chunk = bytes(from_.data[first:last])
    if (
        isinstance(at, bool)
        or not isinstance(at, int)
        or at < 0
        or at + len(chunk) > len(to)
    ):
        raise LispTypeError(f"bytevector-copy!: destination index {at} out of range")
    # ``chunk`` is already a snapshot, so overlapping source/destination works.
    to.data[at : at + len(chunk)] = chunk
    return NIL


def _bytevector_append(*vectors: Any) -> ByteVector:
    out = bytearray()
    for vector in vectors:
        out.extend(_expect_bytevector(vector, "bytevector-append").data)
    return ByteVector(out)


def _utf8_to_string(bv: Any, start: int = 0, end: Optional[int] = None) -> str:
    value = _expect_bytevector(bv, "utf8->string")
    first, last = _bytevector_range(value, start, end, "utf8->string")
    try:
        return bytes(value.data[first:last]).decode("utf-8")
    except UnicodeDecodeError as error:
        raise LispTypeError(
            f"utf8->string: invalid UTF-8 ({error.reason})"
        ) from None


def _string_to_utf8(s: Any, start: int = 0, end: Optional[int] = None) -> ByteVector:
    text = _expect_string(s)
    if start is None:
        start = 0
    if end is None:
        end = len(text)
    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or not 0 <= start <= end <= len(text)
    ):
        raise LispTypeError(f"string->utf8: bad range {start}..{end} for length {len(text)}")
    try:
        return ByteVector(text[start:end].encode("utf-8"))
    except UnicodeEncodeError as error:
        raise LispTypeError(
            f"string->utf8: cannot encode ({error.reason})"
        ) from None


def _expect_hash(h: Any) -> HashTable:
    if isinstance(h, HashTable):
        return h
    raise LispTypeError(f"expected a hash table, got {type(h).__name__}")


def _hash_set(h: Any, key: Any, value: Any) -> Any:
    _expect_hash(h).set(key, value)
    return NIL


def _hash_clear(h: Any) -> Any:
    _expect_hash(h).clear()
    return NIL


def _hash_ref(h: Any, key: Any, failure: Any = None) -> Any:
    table = _expect_hash(h)
    if table.has(key):
        return table.get(key)
    if failure is None:
        raise LispRaise(ErrorObject(f"hash-table-ref: no value for key", [key]))
    if is_procedure(failure):
        return apply_procedure(failure, [])
    return failure


def _hash_update(h: Any, key: Any, proc: Any, default: Any = False) -> Any:
    table = _expect_hash(h)
    current = table.get(key, default)
    table.set(key, apply_procedure(proc, [current]))
    return NIL


# --------------------------------------------------------------------------- #
#  Tagged values                                                               #
# --------------------------------------------------------------------------- #

def _make_tag(tag: Any, fields: Any) -> Tagged:
    return make_tagged(tag, fields)


def _tag_of(value: Any) -> Any:
    if not isinstance(value, Tagged):
        raise LispTypeError(f"tag-of: expected a tagged value, got {to_string(value, write=True)}")
    return value.tag


def _tag_fields(value: Any) -> Any:
    if not isinstance(value, Tagged):
        raise LispTypeError(
            f"tag-fields: expected a tagged value, got {to_string(value, write=True)}"
        )
    return make_list(value.fields)


def _variant_tags(name: Any) -> Any:
    tags = variant_tags(name)
    return make_list(tags) if tags is not None else False


def _variant_of(tag: Any) -> Any:
    union = variant_of(tag)
    return union if union is not None else False


# --------------------------------------------------------------------------- #
#  Conditions, multiple values, and continuations                              #
# --------------------------------------------------------------------------- #

def _raise(value: Any) -> Any:
    raise LispRaise(value)


def _raise_continuable(value: Any) -> Any:
    """``(raise-continuable obj)`` — the handler may return, and the call continues."""
    raise LispRaise(value, continuable=True)


def _error_slot(e: Any, name: str) -> Any:
    if not isinstance(e, ErrorObject):
        raise LispTypeError(f"expected an error object, got {type(e).__name__}")
    return getattr(e, name)


def _as_condition(exc: LispError) -> Any:
    """The object a handler sees: what was raised, or a fresh error object."""
    if isinstance(exc, LispRaise):
        return exc.value
    from .errors import FileError, ReadError

    kind = "file" if isinstance(exc, FileError) else "read" if isinstance(exc, ReadError) else None
    return ErrorObject(str(exc), kind=kind)


def _with_exception_handler(handler: Any, thunk: Any) -> Any:
    """Run *thunk*; a condition goes to *handler*, and if it returns, re-raise.

    A *continuable* condition (from ``(raise-continuable ...)``) is the one
    exception to the re-raise: the handler's return value becomes the value
    of the call, which is what R7RS's ``raise-continuable`` means.
    """
    try:
        return apply_procedure(thunk, [])
    except LispError as exc:
        condition = _as_condition(exc)
        result = apply_procedure(handler, [condition])
        if isinstance(exc, LispRaise) and exc.continuable:
            return result
        raise LispRaise(condition) from None


def _dynamic_wind(before: Any, thunk: Any, after: Any) -> Any:
    """Run *before*, then *thunk*, and *after* whichever way *thunk* exits."""
    apply_procedure(before, [])
    try:
        return apply_procedure(thunk, [])
    finally:
        apply_procedure(after, [])


def _values(*args: Any) -> Any:
    if len(args) == 1:
        return args[0]
    return Values(args)


def _call_with_values(producer: Any, consumer: Any) -> Any:
    result = apply_procedure(producer, [])
    args = list(result) if isinstance(result, Values) else [result]
    return apply_procedure(consumer, args)


def _call_cc(receiver: Any) -> Any:
    """``call/cc`` with an *escape* continuation.

    Invoking the continuation unwinds to this ``call/cc`` with the given value
    — the shape ``(call/cc (lambda (k) (k 1)))`` and every early-exit use of
    ``call/cc`` need. Re-entering an already-exited extent is not supported.
    """
    token = object()

    def escape(*args: Any) -> Any:
        value = args[0] if len(args) == 1 else Values(args)
        raise ContinuationJump(token, value)

    try:
        return apply_procedure(receiver, [Primitive("continuation", escape)])
    except ContinuationJump as jump:
        if jump.token is token:
            return jump.value
        raise


def _apply(f: Any, *args: Any) -> Any:
    """R7RS ``apply``: ``(apply f a b ... xs)`` — leading arguments, then *xs*.

    The last argument is the list to spread; everything before it is passed
    through untouched. So ``(apply + 1 2 (list 3 4))`` is ``(+ 1 2 3 4)``.
    """
    if not args:
        raise LispTypeError("apply: expected a procedure and a list to spread")
    *leading, last = args
    return apply_procedure(f, [*leading, *_expect_list(last, "apply")])


def _expect_environment(value: Any, who: str) -> Environment:
    if isinstance(value, Environment):
        return value
    raise LispTypeError(f"{who}: expected an environment, got {type(value).__name__}")


def _environment(base: Environment, specs: tuple) -> Environment:
    """``(environment import-spec ...)`` — a fresh env with the imports bound.

    Backed by the real library system (:mod:`shslisp.library`): each named
    library is resolved through the registry and its exports bound into a
    fresh child of *base*. A name that is not in the registry is a clear
    "no such library", and one that is declared but not implemented says so.
    """
    from .library import environment_from_specs

    return environment_from_specs(base, specs)


def _procedure_arity(f: Any) -> Any:
    """How many required arguments *f* takes; ``#f`` when that is not fixed.

    Only a Lisp closure records its parameters — a host primitive is an opaque
    Python callable — so this answers for closures and says ``#f`` for the
    rest, including a variadic closure (whose minimum is not its arity).
    """
    if isinstance(f, Closure) and f.rest is None:
        return len(f.params)
    return False


def _substring(s: Any, start: int, end: Optional[int] = None) -> str:
    text = _expect_string(s)
    stop = len(text) if end is None else end
    if not 0 <= start <= stop <= len(text):
        raise LispTypeError(
            f"substring: range [{start}, {stop}) is outside the string's 0..{len(text)}"
        )
    return text[start:stop]


def _string_to_number(s: Any, radix: int = 10) -> Any:
    text = _expect_string(s).strip()
    if radix != 10:
        if radix not in (2, 8, 10, 16):
            raise LispTypeError(
                f"string->number: radix must be 2, 8, 10, or 16, got {radix}"
            )
        try:
            return int(text, radix)
        except ValueError:
            return False
    # C3: the reader's twin, for real — one parser, two entrances. The
    # reader's full syntax parses here: the prefixes (``#e1.5`` is ``3/2``,
    # ``#x10`` is ``16``), the inexact specials, and the complex literals
    # (``1+2i``, row 14). Where the reader raises — ``1/0`` — the string
    # form politely declines: a literal in source means it (row 20), but a
    # conversion may fail.
    try:
        value = _number_from_literal(text)
    except LispSyntaxError:
        return False
    return False if value is NOT_A_NUMBER else value


def _strings_in_step(strings: tuple, who: str) -> list:
    """The character columns of a multi-string walk, equal length required."""
    if not strings:
        raise LispTypeError(f"{who}: expected at least one string")
    cols = [_expect_string(s) for s in strings]
    lengths = sorted({len(col) for col in cols})
    if len(lengths) > 1:
        raise LispTypeError(
            f"{who}: strings must be the same length, got "
            + ", ".join(str(n) for n in lengths)
        )
    return cols


def _string_map(f: Any, *strings: Any) -> str:
    cols = _strings_in_step(strings, "string-map")
    return "".join(
        _expect_char(apply_procedure(f, [_char(c) for c in row]))
        for row in zip(*cols)
    )


def _string_for_each(f: Any, *strings: Any) -> Any:
    cols = _strings_in_step(strings, "string-for-each")
    for row in zip(*cols):
        apply_procedure(f, [_char(c) for c in row])
    return NIL


def _list_set(xs: Any, index: int, value: Any) -> Any:
    if not isinstance(xs, list):
        raise LispTypeError("list-set!: expected a proper (mutable) list")
    if index < 0 or index >= len(xs):
        raise LispTypeError(f"list-set!: index {index} out of range")
    xs[index] = value
    return NIL


# --------------------------------------------------------------------------- #
#  Ports — the mechanism behind display, write, and file I/O                    #
# --------------------------------------------------------------------------- #

def _expect_port(x: Any, who: str) -> Port:
    if isinstance(x, Port):
        return x
    raise LispTypeError(f"{who}: expected a port, got {type(x).__name__}")


def _port_output(x: Any, who: str, binary: bool = False) -> Port:
    port = _expect_port(x, who)
    if not port.writable:
        raise LispTypeError(f"{who}: {port.name} is not an output port")
    if port.closed:
        raise LispTypeError(f"{who}: {port.name} is closed")
    if port.binary != binary:
        kind = "binary" if binary else "textual"
        raise LispTypeError(f"{who}: {port.name} is not a {kind} port")
    return port


def _port_input(x: Any, who: str, binary: bool = False) -> Port:
    port = _expect_port(x, who)
    if not port.readable:
        raise LispTypeError(f"{who}: {port.name} is not an input port")
    if port.closed:
        raise LispTypeError(f"{who}: {port.name} is closed")
    if port.binary != binary:
        kind = "binary" if binary else "textual"
        raise LispTypeError(f"{who}: {port.name} is not a {kind} port")
    return port


def _write_string_to(port: Any, text: str) -> Any:
    stream = _port_output(port, "write-string").stream
    stream.write(text)
    stream.flush()
    return NIL


def _open_input_string(s: Any) -> Port:
    return Port(io.StringIO(_expect_string(s)), readable=True, name="<string>")


def _open_output_string() -> Port:
    return Port(io.StringIO(), writable=True, name="<string>")


def _get_output_string(port: Any) -> str:
    return _expect_port(port, "get-output-string").stream.getvalue()


def _open_file(path: Any, mode: str, who: str, readable: bool, writable: bool) -> Port:
    name = _expect_string(path)
    try:
        stream = open(name, mode, encoding="utf-8")  # noqa: SIM115 - closed by close-port
    except OSError as exc:
        raise FileError(f"{who}: {exc}") from None
    return Port(stream, readable=readable, writable=writable, name=name)


def _close_port(port: Any) -> Any:
    _expect_port(port, "close-port").close()
    return NIL


def _close_direction(port: Any, who: str, want_input: bool) -> Any:
    value = _expect_port(port, who)
    if want_input and not value.readable:
        raise LispTypeError(f"{who}: {value.name} is not an input port")
    if not want_input and not value.writable:
        raise LispTypeError(f"{who}: {value.name} is not an output port")
    value.close()
    return NIL


def _flush_port(port: Any) -> Any:
    _port_output(port, "flush-output-port").stream.flush()
    return NIL


def _read_char(port: Any) -> Any:
    source = _port_input(port, "read-char")
    if source.buffer:
        ch, source.buffer = source.buffer[0], source.buffer[1:]
        return _char(ch)
    ch = source.stream.read(1)
    return EOF if ch == "" else _char(ch)


def _peek_char(port: Any) -> Any:
    source = _port_input(port, "peek-char")
    if source.buffer:
        return _char(source.buffer[0])
    try:
        position = source.stream.tell()
    except (OSError, ValueError):
        raise LispTypeError("peek-char: this port cannot be peeked") from None
    ch = source.stream.read(1)
    source.stream.seek(position)
    return EOF if ch == "" else _char(ch)


def _read_line(port: Any) -> Any:
    source = _port_input(port, "read-line")
    if source.buffer:
        head, sep, rest = source.buffer.partition("\n")
        if sep:
            source.buffer = rest
            return head[:-1] if head.endswith("\r") else head
        source.buffer = ""
        line = head + source.stream.readline()
    else:
        line = source.stream.readline()
    if line == "":
        return EOF
    if line.endswith("\n"):
        line = line[:-1]
        if line.endswith("\r"):
            line = line[:-1]
    return line


def _char_ready(port: Any) -> bool:
    # A string or file port always has its bytes to hand; a real terminal is the
    # host's business. Answering #t is the honest, portable reading for the
    # streams this language actually opens.
    _port_input(port, "char-ready?")
    return True


def _call_with_port(port: Any, proc: Any) -> Any:
    """``(call-with-port port proc)`` — apply *proc*, then close the port."""
    _expect_port(port, "call-with-port")
    try:
        return apply_procedure(proc, [port])
    finally:
        port.close()


#: Reader errors that mean "the datum is not complete yet", not "the datum is
#: malformed". ``read`` on a stream grows its buffer until one of these clears.
#: ``nothing follows`` covers the prefixes that take a second character — ``'``,
#: ``,``, ``#\`` — which on a complete document are errors and on a stream are
#: just a boundary the reader has not reached yet.
_INCOMPLETE_READ = (
    "unexpected end of input",
    "nothing follows",
    "missing )",
    "unterminated string literal",
    "unterminated escape in string",
    "unterminated \\x escape",
    "unterminated block comment",
    "unterminated |quoted symbol|",
)


def _read_datum(port: Any) -> Any:
    """``(read [port])`` — one datum, leaving the rest of the stream in place.

    Characters are pulled only until the first datum is complete, rather than
    reading the whole stream to EOF. That keeps ``read`` usable on an
    interactive port (and on a pipe that stays open): the next call sees the
    characters after this datum in ``port.buffer``.
    """
    from .reader import read_one_at

    source = _port_input(port, "read")
    text = source.buffer
    while True:
        try:
            form, end, source.fold_case = read_one_at(text, 0, source.fold_case)
        except LispSyntaxError as error:
            message = str(error)
            if any(fragment in message for fragment in _INCOMPLETE_READ):
                chunk = source.stream.read(1)
                if chunk == "":
                    source.buffer = ""
                    if not text.strip():
                        return EOF
                    raise ReadError(f"read: {error}") from None
                text += chunk
                continue
            source.buffer = ""
            raise ReadError(f"read: {error}") from None
        source.buffer = text[end:]
        return form


def _read_string(count: Any, port: Any) -> Any:
    """R7RS ``(read-string k [port])`` — up to *k* characters.

    Returns a string of at most *k* characters; at end of input it returns the
    shorter remainder, or the eof object when no characters are available.
    """
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise LispTypeError(
            f"read-string: expected a non-negative exact integer, got {count!r}"
        )
    source = _port_input(port, "read-string")
    if count == 0:
        return ""
    text = source.buffer
    source.buffer = ""
    if len(text) < count:
        text += source.stream.read(count - len(text))
    if text == "":
        return EOF
    source.buffer = text[count:]
    return text[:count]


def _open_input_bytevector(bv: Any) -> Port:
    return Port(
        io.BytesIO(bytes(_expect_bytevector(bv, "open-input-bytevector").data)),
        readable=True,
        name="<bytevector>",
        binary=True,
    )


def _open_output_bytevector() -> Port:
    return Port(io.BytesIO(), writable=True, name="<bytevector>", binary=True)


def _get_output_bytevector(port: Any) -> ByteVector:
    return ByteVector(_port_output(port, "get-output-bytevector", binary=True).stream.getvalue())


def _open_binary_file(path: Any, mode: str, who: str, readable: bool, writable: bool) -> Port:
    name = _expect_string(path)
    try:
        stream = open(name, mode)  # noqa: SIM115 - closed by the port
    except OSError as exc:
        raise FileError(f"{who}: {exc}") from None
    return Port(stream, readable=readable, writable=writable, name=name, binary=True)


def _read_u8(port: Any) -> Any:
    chunk = _port_input(port, "read-u8", binary=True).stream.read(1)
    return EOF if chunk == b"" else chunk[0]


def _peek_u8(port: Any) -> Any:
    source = _port_input(port, "peek-u8", binary=True)
    try:
        position = source.stream.tell()
    except (OSError, ValueError):
        raise LispTypeError("peek-u8: this port cannot be peeked") from None
    chunk = source.stream.read(1)
    source.stream.seek(position)
    return EOF if chunk == b"" else chunk[0]


def _u8_ready(port: Any) -> bool:
    _port_input(port, "u8-ready?", binary=True)
    return True


def _write_u8(byte: Any, port: Any) -> Any:
    _port_output(port, "write-u8", binary=True).stream.write(
        bytes([_expect_u8(byte, "write-u8")])
    )
    return NIL


def _read_bytevector(count: Any, port: Any) -> Any:
    source = _port_input(port, "read-bytevector", binary=True)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise LispTypeError("read-bytevector: expected a non-negative count")
    chunk = source.stream.read(count)
    return EOF if chunk == b"" else ByteVector(chunk)


def _read_bytevector_into(
    bv: Any,
    port: Any,
    start: int = 0,
    end: Optional[int] = None,
) -> Any:
    source = _port_input(port, "read-bytevector!", binary=True)
    target = _expect_bytevector(bv, "read-bytevector!")
    stop = len(target) if end is None else end
    if not 0 <= start <= stop <= len(target):
        raise LispTypeError(f"read-bytevector!: range {start}..{stop} out of range")
    chunk = source.stream.read(stop - start)
    if chunk == b"" and stop > start:
        return EOF
    target.data[start : start + len(chunk)] = chunk
    return len(chunk)


def _write_bytevector(
    bv: Any,
    port: Any,
    start: int = 0,
    end: Optional[int] = None,
) -> Any:
    sink = _port_output(port, "write-bytevector", binary=True)
    source = _expect_bytevector(bv, "write-bytevector")
    stop = len(source) if end is None else end
    if not 0 <= start <= stop <= len(source):
        raise LispTypeError(f"write-bytevector: range {start}..{stop} out of range")
    sink.stream.write(bytes(source.data[start:stop]))
    return NIL


def _file_exists(path: Any) -> bool:
    return os.path.exists(_expect_string(path))


def _delete_file(path: Any) -> Any:
    name = _expect_string(path)
    try:
        os.remove(name)
    except OSError as exc:
        raise FileError(f"delete-file: {exc}") from None
    return NIL


def _environment_variables() -> list:
    return [[name, value] for name, value in sorted(os.environ.items())]


def _get_env(name: str) -> Any:
    value = os.environ.get(name)
    return False if value is None else value


def _exit(code: tuple, emergency: bool = False) -> Any:
    """``(exit [obj])`` — leave the host. ``#t`` → 0, ``#f`` → 1, integer → it."""
    if not code or is_nil(code[0]):
        status = 0
    elif code[0] is True or code[0] is False:
        status = 0 if code[0] is True else 1
    else:
        status = int(_expect_number(code[0], "exit"))
    if not emergency:
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except (OSError, ValueError):  # pragma: no cover - host-dependent
                pass
    raise SystemExit(status)



def _expect_string(x: Any) -> str:
    if isinstance(x, MutableString):
        return x.text
    if isinstance(x, str) and not isinstance(x, (Symbol, Keyword)):
        return x
    raise LispTypeError(f"expected a string, got {type(x).__name__}")


def _expect_keyword(x: Any) -> Keyword:
    if is_keyword(x):
        return x
    raise LispTypeError(f"expected a keyword, got {type(x).__name__}")


def _expect_mutable_string(x: Any, who: str) -> MutableString:
    if isinstance(x, MutableString):
        return x
    if isinstance(x, str) and not isinstance(x, Symbol):
        raise LispTypeError(f"{who}: string literals are immutable")
    raise LispTypeError(f"{who}: expected a string, got {type(x).__name__}")


def _read_first(text: Any) -> Any:
    forms = read_all(_expect_string(text))
    if not forms:
        return NIL
    return forms[0]


def _error(*args: Any) -> Any:
    # R7RS: (error message obj ...) — the message is the first argument, the
    # rest are irritants. A non-string message is rendered as if by `write`.
    if not args:
        message, irritants = "error", []
    else:
        first = args[0]
        if isinstance(first, str) and not isinstance(first, Symbol):
            message = first
        else:
            message = to_string(first, write=True)
        irritants = list(args[1:])
    raise LispRaise(ErrorObject(message, irritants))


def _assert(condition: Any, *message: Any) -> Any:
    if not is_true(condition):
        detail = " ".join(to_string(m, write=False) for m in message)
        text = f"assertion failed: {detail}" if detail else "assertion failed"
        raise LispRaise(ErrorObject(text))
    return NIL


def _gensym() -> Callable[[], Symbol]:
    counter = {"n": 0}

    def fresh() -> Symbol:
        counter["n"] += 1
        return intern(f"g{counter['n']}")

    return fresh
